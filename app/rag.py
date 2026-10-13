"""Search project notes with the configured hosted or local vector store."""
import hashlib
import json
import re
from pathlib import Path
from threading import Lock, RLock

import numpy as np

from .config import settings
from .fileio import atomic_write_json
from .parsers import extract_text

LOCAL_DIM = 512


def chunk(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return [c for c in out if len(c) > 40]


class Embedder:
    def __init__(self):
        self.pc_model = settings.pinecone_embed_model if settings.pinecone_api_key else ""
        self.dim = 1024 if self.pc_model else LOCAL_DIM
        self._pc = None

    def _local(self, text: str) -> list[float]:
        toks = re.findall(r"[a-z0-9]+", text.lower())
        feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
        v = np.zeros(LOCAL_DIM)
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            v[h % LOCAL_DIM] += 1.0 if (h >> 64) % 2 else -1.0
            v[(h >> 8) % LOCAL_DIM] += 0.5
        n = np.linalg.norm(v) or 1.0
        return (v / n).tolist()

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        if not self.pc_model:
            return [self._local(t) for t in texts]
        from pinecone import Pinecone

        self._pc = self._pc or Pinecone(api_key=settings.pinecone_api_key)
        res = self._pc.inference.embed(model=self.pc_model, inputs=texts,
                                       parameters={"input_type": "query" if query else "passage"})
        return [r["values"] for r in res]


class LocalStore:
    def __init__(self):
        self.path = settings.data_dir / "kb" / "local.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.rows = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def upsert(self, rows):
        with self._lock:
            ids = {r["id"] for r in rows}
            self.rows = [r for r in self.rows if r["id"] not in ids] + rows
            atomic_write_json(self.path, self.rows)

    def query(self, vec, k):
        with self._lock:
            if not self.rows:
                return []
            matrix = np.array([row["vec"] for row in self.rows])
            scores = matrix @ np.array(vec)
            indexes = np.argsort(-scores)[:k]
            return [
                {
                    **{key: self.rows[index][key] for key in ("title", "text", "source")},
                    "score": float(scores[index]),
                }
                for index in indexes
            ]

    def count(self):
        with self._lock:
            return len(self.rows)


class PineconeStore:
    def __init__(self, dim: int):
        from pinecone import Pinecone, ServerlessSpec

        pc = Pinecone(api_key=settings.pinecone_api_key)
        names = [i["name"] for i in pc.list_indexes()]
        if settings.pinecone_index not in names:
            pc.create_index(name=settings.pinecone_index, dimension=dim, metric="cosine",
                            spec=ServerlessSpec(cloud=settings.pinecone_cloud, region=settings.pinecone_region))
        self.index = pc.Index(settings.pinecone_index)

    def upsert(self, rows):
        self.index.upsert(vectors=[{"id": r["id"], "values": r["vec"],
                                    "metadata": {"title": r["title"], "text": r["text"], "source": r["source"]}}
                                   for r in rows])

    def query(self, vec, k):
        res = self.index.query(vector=vec, top_k=k, include_metadata=True)
        return [{"title": m.metadata.get("title", ""), "text": m.metadata.get("text", ""),
                 "source": m.metadata.get("source", ""), "score": float(m.score)} for m in res.matches]

    def count(self):
        return self.index.describe_index_stats().total_vector_count


class KnowledgeBase:
    def __init__(self):
        self.embedder = Embedder()
        self.store = PineconeStore(self.embedder.dim) if settings.pinecone_api_key else LocalStore()

    @property
    def backend(self) -> str:
        return "pinecone" if settings.pinecone_api_key else "local"

    def ingest_text(self, title: str, text: str, source: str = "") -> int:
        chunks = chunk(text)
        if not chunks:
            return 0
        vecs = self.embedder.embed(chunks)
        base = hashlib.md5((source or title).encode()).hexdigest()[:10]
        self.store.upsert([{"id": f"{base}-{i}", "vec": v, "title": title, "text": c, "source": source or title}
                           for i, (c, v) in enumerate(zip(chunks, vecs))])
        return len(chunks)

    def ingest_file(self, path: str | Path) -> int:
        p = Path(path)
        return self.ingest_text(p.stem.replace("_", " "), extract_text(p), p.name)

    def search(self, query: str, k: int = 5, min_score: float = 0.05) -> list[dict]:
        if self.store.count() == 0:
            return []
        hits = self.store.query(self.embedder.embed([query], query=True)[0], k)
        return [h for h in hits if h["score"] >= min_score]


_kb = None
_kb_lock = Lock()


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        with _kb_lock:
            if _kb is None:
                _kb = KnowledgeBase()
    return _kb


def reset_kb():
    global _kb
    with _kb_lock:
        _kb = None

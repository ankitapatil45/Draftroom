"""Search the web and project notes, then register results as citeable sources."""
from datetime import date
import re
from concurrent.futures import ThreadPoolExecutor

from .. import web
from ..rag import get_kb
from .base import Ctx


class WebResearchAgent:
    name = "web_research"

    def queries(self, ctx: Ctx, topic: str) -> list[str]:
        year = date.today().year
        j = ctx.llm.json("You plan web searches.", f'Give up to 4 diverse, specific search queries (include the year '
                         f'{year} where recency matters) to research: "{topic}". JSON: {{"queries": [..]}}', 400)
        if j and j.get("queries"):
            return [str(q) for q in j["queries"][:4]]
        return [topic, f"{topic} latest trends {year}", f"{topic} market statistics"]

    def run(self, ctx: Ctx, topic: str) -> list[dict]:
        qs = self.queries(ctx, topic)
        with ctx.step(self.name, "search", queries=qs) as out:
            with ThreadPoolExecutor(4) as ex:
                results = [r for rs in ex.map(web.search, qs) for r in rs]
            seen, uniq = set(), []
            for r in results:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    uniq.append(r)
            uniq = uniq[:8]
            with ThreadPoolExecutor(4) as ex:  # enrich top hits with page text
                texts = list(ex.map(lambda r: web.fetch_text(r["url"], 1500), uniq[:4]))
            for r, t in zip(uniq, texts):
                if t:
                    r["snippet"] = (r["snippet"] + " " + t)[:1400]
            srcs = ctx.store.add_sources(ctx.sid, [{**r, "kind": "web"} for r in uniq])
            out["sources"] = [s["id"] for s in srcs]
            return srcs


class RagAgent:
    name = "rag"

    def run(self, ctx: Ctx, topic: str, k: int = 5) -> list[dict]:
        with ctx.step(self.name, "retrieve", query=topic) as out:
            kb = get_kb()
            hits = kb.search(topic, k)
            srcs = ctx.store.add_sources(ctx.sid, [{"title": f"{h['title']} ({h['source']})", "url": "",
                                                    "kind": "kb", "snippet": h["text"]} for h in hits])
            out["backend"] = kb.backend
            out["sources"] = [s["id"] for s in srcs]
            out["scores"] = [round(h["score"], 3) for h in hits]
            return srcs

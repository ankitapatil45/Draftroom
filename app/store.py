"""Persist session state in a database and keep uploaded and generated files on disk."""
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from threading import Lock, RLock, local
from typing import Optional

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import engine, sessions, traces, versions
from .fileio import atomic_write

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    name = Path(name).name
    return _SAFE.sub("_", name)[:120] or "file"


class SessionStore:
    def __init__(self, root: Optional[Path] = None):
        # Files remain on disk; the database stores session and version metadata.
        self.root = Path(root or settings.data_dir) / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock_guard = Lock()
        self._session_locks: dict[str, RLock] = {}
        self._lock_state = local()

    @contextmanager
    def locked_session(self, sid: str):
        """Serialize changes to one session, including across PostgreSQL workers."""
        self.dir(sid)
        with self._lock_guard:
            lock = self._session_locks.setdefault(sid, RLock())
        with lock:
            if engine.dialect.name != "postgresql":
                yield
                return

            # A session can call store methods that lock it again. Reuse the
            # same PostgreSQL connection until the outermost lock is released.
            active_locks = getattr(self._lock_state, "active", {})
            if sid in active_locks:
                active_locks[sid][1] += 1
                try:
                    yield
                finally:
                    active_locks[sid][1] -= 1
                return
            lock_key = int(sid, 16)
            connection = engine.connect()
            try:
                connection.execute(select(func.pg_advisory_lock(lock_key)))
                connection.commit()
                active_locks[sid] = [connection, 1]
                self._lock_state.active = active_locks
                try:
                    yield
                finally:
                    connection.execute(select(func.pg_advisory_unlock(lock_key)))
                    connection.commit()
                    active_locks.pop(sid, None)
                    connection.close()
            except Exception:
                active_locks.pop(sid, None)
                connection.close()
                raise

    def dir(self, sid: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{12}", sid):
            raise KeyError("invalid session id")
        with engine.connect() as connection:
            exists = connection.scalar(select(sessions.c.id).where(sessions.c.id == sid))
        if not exists:
            raise KeyError("unknown session")
        return self.root / sid

    def create(self) -> str:
        sid = uuid.uuid4().hex[:12]
        directory = self.root / sid
        (directory / "uploads").mkdir(parents=True)
        (directory / "versions").mkdir()
        data = {"id": sid, "created": time.time(), "uploads": [], "style": {}, "sources": [], "analyzed": []}
        with engine.begin() as connection:
            connection.execute(insert(sessions).values(id=sid, created=data["created"], data=data))
        return sid

    def get(self, sid: str) -> dict:
        self.dir(sid)
        with engine.connect() as connection:
            data = connection.scalar(select(sessions.c.data).where(sessions.c.id == sid))
        return data

    def _save(self, sid: str, data: dict):
        with engine.begin() as connection:
            connection.execute(update(sessions).where(sessions.c.id == sid).values(data=data))

    def update(self, sid: str, **fields) -> dict:
        with self.locked_session(sid):
            data = self.get(sid)
            data.update(fields)
            self._save(sid, data)
            return data

    def save_upload(self, sid: str, filename: str, data: bytes, kind: str) -> dict:
        with self.locked_session(sid):
            session = self.get(sid)
            name = safe_name(filename)
            path = self.dir(sid) / "uploads" / name
            atomic_write(path, data)
            record = {"name": name, "path": str(path), "kind": kind, "bytes": len(data)}
            session["uploads"] = [u for u in session["uploads"] if u["name"] != name] + [record]
            session["analyzed"] = [a for a in session["analyzed"] if a != name]
            self._save(sid, session)
            return record

    def add_sources(self, sid: str, items: list[dict]) -> list[dict]:
        with self.locked_session(sid):
            session = self.get(sid)
            existing = {(x["url"] or x["title"], x["snippet"][:80]): x for x in session["sources"]}
            output = []
            for item in items:
                key = (item.get("url") or item["title"], item.get("snippet", "")[:80])
                if key in existing:
                    output.append(existing[key])
                    continue
                record = {
                    "id": len(session["sources"]) + 1,
                    "title": item["title"],
                    "url": item.get("url", ""),
                    "kind": item.get("kind", "web"),
                    "snippet": item.get("snippet", ""),
                }
                session["sources"].append(record)
                existing[key] = record
                output.append(record)
            self._save(sid, session)
            return output

    def versions(self, sid: str) -> list[dict]:
        self.dir(sid)
        with engine.connect() as connection:
            states = connection.execute(
                select(versions.c.state)
                .where(versions.c.session_id == sid, versions.c.state.is_not(None))
                .order_by(versions.c.number)
            ).scalars()
            return [{key: state[key] for key in ("number", "parent", "note", "created", "files")} for state in states]

    def latest(self, sid: str) -> Optional[dict]:
        items = self.versions(sid)
        return self.version(sid, items[-1]["number"]) if items else None

    def version(self, sid: str, number: int) -> dict:
        self.dir(sid)
        with engine.connect() as connection:
            state = connection.scalar(
                select(versions.c.state).where(
                    versions.c.session_id == sid,
                    versions.c.number == int(number),
                )
            )
        if state is None:
            raise FileNotFoundError(f"version {number} not found")
        return state

    def version_dir(self, sid: str, number: int) -> Path:
        return self.dir(sid) / "versions" / f"v{int(number)}"

    def new_version_dir(self, sid: str) -> tuple[int, Path]:
        with self.locked_session(sid):
            while True:
                try:
                    with engine.begin() as connection:
                        maximum = connection.scalar(
                            select(func.max(versions.c.number)).where(versions.c.session_id == sid)
                        ) or 0
                        number = maximum + 1
                        connection.execute(insert(versions).values(session_id=sid, number=number, state=None))
                    directory = self.version_dir(sid, number)
                    directory.mkdir(parents=True, exist_ok=True)
                    return number, directory
                except IntegrityError:
                    # Another process reserved the same next version; retry with the new maximum.
                    continue

    def commit_version(self, sid: str, number: int, state: dict):
        """Fill in a version row previously reserved by new_version_dir()."""
        with self.locked_session(sid):
            version_state = {**state, "number": number, "created": time.time()}
            with engine.begin() as connection:
                result = connection.execute(
                    update(versions)
                    .where(versions.c.session_id == sid, versions.c.number == number)
                    .values(state=version_state)
                )
                if not result.rowcount:
                    raise ValueError(f"version {number} was not reserved")

    def abandon_version(self, sid: str, number: int):
        """Remove an uncommitted version reservation and its partial files."""
        with self.locked_session(sid):
            with engine.begin() as connection:
                result = connection.execute(
                    delete(versions).where(
                        versions.c.session_id == sid,
                        versions.c.number == number,
                        versions.c.state.is_(None),
                    )
                )
            if result.rowcount:
                shutil.rmtree(self.version_dir(sid, number), ignore_errors=True)

    def revert(self, sid: str, number: int) -> dict:
        with self.locked_session(sid):
            old = dict(self.version(sid, number))
            new_number, directory = self.new_version_dir(sid)
            for file in self.version_dir(sid, number).iterdir():
                if file.name != "state.json":
                    shutil.copy(file, directory / file.name)
            latest = self.latest(sid)
            old["parent"] = latest["number"] if latest else None
            old["note"] = f"Reverted to v{number}"
            self.commit_version(sid, new_number, old)
            return old

    def trace(self, sid: str, agent: str, action: str, detail: dict, ms: float = 0):
        record = {"t": time.time(), "agent": agent, "action": action, "ms": round(ms, 1), "detail": detail}
        with engine.begin() as connection:
            connection.execute(insert(traces).values(session_id=sid, record=record))

    def get_trace(self, sid: str) -> list[dict]:
        self.dir(sid)
        with engine.connect() as connection:
            return list(
                connection.execute(
                    select(traces.c.record).where(traces.c.session_id == sid).order_by(traces.c.id)
                ).scalars()
            )

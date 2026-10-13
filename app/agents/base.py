import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from ..llm import LLM, llm
from ..store import SessionStore


@dataclass
class Ctx:
    sid: str
    store: SessionStore
    message: str = ""
    plan: dict = field(default_factory=dict)
    llm: LLM = llm

    def session(self) -> dict:
        return self.store.get(self.sid)

    @contextmanager
    def step(self, agent: str, action: str, **detail) -> Iterator[dict]:
        t = time.time()
        out = {}
        try:
            yield out
        finally:
            self.store.trace(self.sid, agent, action, {**detail, **out}, (time.time() - t) * 1000)

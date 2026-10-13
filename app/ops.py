"""Apply structured edits to documents and slide decks."""
import re
from typing import Optional

from .models import CITE_RE, DeckIR, DocIR, Section, Slide


def sentences(text: str) -> list[str]:
    out = []
    for s in (x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()):
        if out and re.fullmatch(r"(\[\d+\]\s*)+[.!?]?", s):  # citation marker split off its sentence
            out[-1] += " " + s
        else:
            out.append(s)
    return out


def trim_words(text: str, max_words: int) -> str:
    cites = "".join(f" [{m}]" for m in CITE_RE.findall(text))
    clean = CITE_RE.sub("", text).strip()
    w = clean.split()
    if len(w) <= max_words:
        return text
    return " ".join(w[:max_words]).rstrip(",;:") + "…" + cites


def _find(items, match: str, attr: str) -> Optional[int]:
    m = match.lower().strip()
    for i, it in enumerate(items):
        if getattr(it, attr).lower().strip() == m:
            return i
    for i, it in enumerate(items):
        if m in getattr(it, attr).lower() or getattr(it, attr).lower() in m:
            return i
    return None


def apply_op(doc: Optional[DocIR], deck: Optional[DeckIR], op: dict) -> str:
    """Returns a short human-readable description of what changed ('' if nothing)."""
    scope, kind = op.get("scope", "doc"), op.get("op")
    target = doc if scope == "doc" else deck
    if target is None:
        return ""
    items = target.sections if scope == "doc" else target.slides
    attr = "heading" if scope == "doc" else "title"
    Item = Section if scope == "doc" else Slide

    if kind == "add":
        new = Item(**op["item"])
        after = op.get("after")
        if after == "start":
            idx = 0 if scope == "doc" else (1 if items and items[0].kind == "title" else 0)
        elif after:
            j = _find(items, after, attr)
            idx = (j + 1) if j is not None else len(items)
        else:
            idx = len(items)
        if scope == "deck" and items and items[-1].kind == "sources":
            idx = min(idx, len(items) - 1)
        items.insert(idx, new)
        return f"added {'section' if scope == 'doc' else 'slide'} '{getattr(new, attr)}'"
    if kind == "update":
        j = _find(items, op["match"], attr)
        if j is None:
            return ""
        items[j] = Item(**{**items[j].model_dump(), **op["item"]})
        return f"updated '{getattr(items[j], attr)}'"
    if kind == "remove":
        j = _find(items, op["match"], attr)
        if j is None:
            return ""
        gone = items.pop(j)
        return f"removed '{getattr(gone, attr)}'"
    if kind == "condense":
        mb, mw = op.get("max_bullets", 4), op.get("max_words", 14)
        ms = op.get("max_sentences", 2)
        for it in items:
            it.bullets = [trim_words(b, mw) for b in it.bullets[:mb]]
            if scope == "doc":
                it.paragraphs = [" ".join(sentences(p)[:ms]) for p in it.paragraphs[:2]]
            elif getattr(it, "notes", ""):
                it.notes = " ".join(sentences(it.notes)[:1])
        return f"condensed to ≤{mb} bullets × {mw} words"
    return ""

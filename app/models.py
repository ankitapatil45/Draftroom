"""Structured document, slide, and source models used throughout the app."""
import re
from typing import Optional

from pydantic import BaseModel, Field


class Section(BaseModel):
    heading: str
    level: int = 1
    paragraphs: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class DocIR(BaseModel):
    title: str
    subtitle: str = ""
    sections: list[Section] = Field(default_factory=list)


class Slide(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)
    notes: str = ""
    kind: str = "content"  # title | content | sources


class DeckIR(BaseModel):
    title: str
    subtitle: str = ""
    slides: list[Slide] = Field(default_factory=list)


class Source(BaseModel):
    id: int
    title: str
    url: str = ""
    kind: str = "web"  # web | kb | upload
    snippet: str = ""


CITE_RE = re.compile(r"\[(\d+)\]")


def doc_text(doc: DocIR) -> str:
    parts = [doc.title, doc.subtitle]
    for s in doc.sections:
        parts += [s.heading, *s.paragraphs, *s.bullets]
    return "\n".join(p for p in parts if p)


def deck_text(deck: DeckIR) -> str:
    parts = [deck.title, deck.subtitle]
    for s in deck.slides:
        parts += [s.title, *s.bullets, s.notes]
    return "\n".join(p for p in parts if p)


def cited_ids(doc: Optional[DocIR] = None, deck: Optional[DeckIR] = None) -> set[int]:
    text = (doc_text(doc) if doc else "") + "\n" + (deck_text(deck) if deck else "")
    return {int(m) for m in CITE_RE.findall(text)}

"""Convert between structured document and presentation content."""
from pydantic import ValidationError

from ..models import CITE_RE, DeckIR, DocIR, Section, Slide
from ..ops import sentences, trim_words
from .base import Ctx


def doc_to_deck(doc: DocIR, max_slides: int | None = None) -> DeckIR:
    slides = []
    for s in doc.sections:
        pts = list(s.bullets)
        for p in s.paragraphs:
            for sent in sentences(p):
                pts.append(sent)
        bullets = [trim_words(p, 16) for p in pts[:4]]
        if bullets:
            slides.append(Slide(title=s.heading, bullets=bullets, notes=" ".join(s.paragraphs)[:600]))
    if max_slides:
        slides = slides[:max_slides]
    return DeckIR(title=doc.title, subtitle=doc.subtitle, slides=slides)


def deck_to_doc(deck: DeckIR) -> DocIR:
    secs = []
    for s in deck.slides:
        if s.kind in ("title", "sources"):
            continue
        sec = Section(heading=s.title, bullets=list(s.bullets))
        if s.notes:
            sec.paragraphs.append(s.notes)
        secs.append(sec)
    return DocIR(title=deck.title, subtitle=deck.subtitle, sections=secs)


class ConverterAgent:
    name = "converter"

    def run(self, ctx: Ctx, direction: str, doc: DocIR | None, deck: DeckIR | None, n_slides: int | None):
        with ctx.step(self.name, "convert", direction=direction) as out:
            if direction == "doc_to_deck" and doc:
                if ctx.llm.live:
                    j = ctx.llm.json("Convert a document into a concise presentation. Keep [n] citations. Title slide "
                                     "kind 'title', final 'sources' slide optional.",
                                     f"Slides wanted: {n_slides or 'auto'}\nDOC:\n{doc.model_dump_json()}\nSchema: "
                                     '{"title":str,"subtitle":str,"slides":[{"title":str,"bullets":[str],"notes":str,"kind":"content"}]}')
                    if j:
                        try:
                            out["mode"] = "llm"
                            return None, DeckIR(**j)
                        except ValidationError:
                            # Invalid model output is handled by the local converter.
                            pass
                out["mode"] = "fallback"
                return None, doc_to_deck(doc, (n_slides - 2) if n_slides else None)
            if direction == "deck_to_doc" and deck:
                if ctx.llm.live:
                    j = ctx.llm.json("Convert a slide deck into a well-written document in prose + bullets. Keep [n] citations.",
                                     f"DECK:\n{deck.model_dump_json()}\nSchema: "
                                     '{"title":str,"subtitle":str,"sections":[{"heading":str,"level":1,"paragraphs":[str],"bullets":[str]}]}')
                    if j:
                        try:
                            out["mode"] = "llm"
                            return DocIR(**j), None
                        except ValidationError:
                            # Invalid model output is handled by the local converter.
                            pass
                out["mode"] = "fallback"
                return deck_to_doc(deck), None
        return None, None

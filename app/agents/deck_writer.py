"""Create structured presentation content before rendering it to PowerPoint."""
from pydantic import ValidationError

from ..models import DeckIR, DocIR, Slide
from ..ops import sentences, trim_words
from .base import Ctx
from .writing_common import DECK_SCHEMA, sentence_pool, source_block, style_block, topic_title


class DeckWriterAgent:
    name = "deck_writer"

    def run(
        self,
        ctx: Ctx,
        topic: str,
        sources: list[dict],
        n_slides: int,
        doc: DocIR | None,
        feedback: str = "",
    ) -> DeckIR:
        style = ctx.session().get("style", {})
        with ctx.step(self.name, "write", topic=topic, slides=n_slides) as out:
            outline = [section.heading for section in doc.sections] if doc else []
            result = ctx.llm.json(
                f"You are a presentation writer. Produce EXACTLY {n_slides} slides in total: slide 1 is the title slide "
                f"(kind 'title'), the last is 'Sources' (kind 'sources'), the rest are content slides with 3-5 short "
                "bullets (<=14 words each) and speaker notes. Match the template's tone and slide-title style. Cite "
                "sources inline as [n]. Never invent facts.",
                f"REQUEST: {ctx.message}\nTOPIC: {topic}\nTEMPLATE PROFILE:\n{style_block(style, 'deck')}\n"
                f"COMPANION DOCUMENT OUTLINE: {outline}\nSOURCES:\n{source_block(sources, 600)}\n"
                f"VALIDATION FEEDBACK TO FIX: {feedback or 'none'}\nReturn JSON schema: {DECK_SCHEMA}",
            )
            if result:
                try:
                    deck = DeckIR(**result)
                    out["mode"] = "llm"
                    return deck
                except ValidationError:
                    # Malformed model output falls back to deterministic content.
                    pass

            out["mode"] = "fallback"
            return self.fallback(topic, sources, n_slides, doc)

    def fallback(
        self,
        topic: str,
        sources: list[dict],
        n_slides: int,
        doc: DocIR | None,
    ) -> DeckIR:
        from .converter import doc_to_deck

        deck = doc_to_deck(doc) if doc else DeckIR(title=topic_title(topic), slides=[])
        if not doc:
            for source in sources:
                bullets = [
                    f"{trim_words(sentence, 14)} [{source['id']}]"
                    for sentence in sentences(source["snippet"])[:3]
                ]
                deck.slides.append(Slide(title=trim_words(source["title"], 7), bullets=bullets))

        wanted_content = max(n_slides - 2, 1)
        content = [slide for slide in deck.slides if slide.kind == "content"]
        pool = sentence_pool(sources)
        titles = {source["id"]: source["title"] for source in sources}
        index = 0
        while len(content) < wanted_content and pool:
            chunk = [pool[(index + offset) % len(pool)] for offset in range(min(3, len(pool)))]
            index += 3
            title = f"Insight {len(content) + 1}: {trim_words(titles[chunk[0][1]], 5)}"
            bullets = [f"{trim_words(text, 14)} [{source_id}]" for text, source_id in chunk]
            content.append(Slide(title=title, bullets=bullets))

        deck.slides = content[:wanted_content]
        return deck

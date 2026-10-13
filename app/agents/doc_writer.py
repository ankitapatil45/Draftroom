"""Create document content as a DocIR before it is rendered to Word."""
from pydantic import ValidationError

from ..models import DocIR, Section
from ..ops import trim_words
from .base import Ctx
from .writing_common import DOC_SCHEMA, sentence_pool, source_block, style_block, topic_title


class DocWriterAgent:
    name = "doc_writer"

    def run(self, ctx: Ctx, topic: str, sources: list[dict], feedback: str = "") -> DocIR:
        style = ctx.session().get("style", {})
        with ctx.step(self.name, "write", topic=topic, n_sources=len(sources)) as out:
            result = ctx.llm.json(
                "You are an enterprise proposal writer. Write a complete professional document in the SAME tone, "
                "voice and section structure as the template profile. Ground every factual claim in the numbered "
                "sources and cite them inline as [n]. Never invent facts or sources; if evidence is missing, say so.",
                f"REQUEST: {ctx.message}\nTOPIC: {topic}\nTEMPLATE PROFILE:\n{style_block(style, 'doc')}\n"
                f"SOURCES:\n{source_block(sources)}\nVALIDATION FEEDBACK TO FIX: {feedback or 'none'}\n"
                f"Return JSON schema: {DOC_SCHEMA}",
            )
            if result:
                try:
                    document = DocIR(**result)
                    out["mode"] = "llm"
                    return document
                except ValidationError:
                    # Malformed model output falls back to deterministic content.
                    pass

            out["mode"] = "fallback"
            return self.fallback(topic, sources, style)

    def fallback(self, topic: str, sources: list[dict], style: dict) -> DocIR:
        headings = [
            item["text"]
            for item in (style.get("doc") or {}).get("headings", [])
            if item["level"] == 1
        ][:6]
        if len(headings) < 3:
            headings = [
                "Executive Summary",
                "Background",
                "Key Findings",
                "Recommended Approach",
                "Next Steps",
            ]

        pool = sentence_pool(sources)
        sections, index = [], 0
        for heading in headings:
            section = Section(heading=heading)
            if pool:
                for _ in range(2):
                    sentence, source_id = pool[index % len(pool)]
                    index += 1
                    section.paragraphs.append(f"{trim_words(sentence, 45)} [{source_id}]")
            else:
                section.paragraphs.append("No supporting evidence was retrieved for this section.")
            sections.append(section)

        return DocIR(
            title=topic_title(topic),
            subtitle="Prepared from the available sources",
            sections=sections,
        )

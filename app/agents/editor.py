"""Turn edit requests into structured operations for documents and slides."""
import re

from ..models import DeckIR, DocIR, Section, Slide
from ..ops import sentences, trim_words
from .base import Ctx

OPS_SPEC = """Return {"summary": str, "refresh": bool, "ops": [op,...]} where op is one of
{"scope":"doc"|"deck","op":"add","after":"<heading/title>|start","item":<Section|Slide object>}
{"scope":..,"op":"update","match":"<heading/title>","item":{only fields to change}}
{"scope":..,"op":"remove","match":"<heading/title>"}
{"scope":..,"op":"condense","max_bullets":int,"max_words":int,"max_sentences":int}
Section={"heading","level","paragraphs","bullets"}  Slide={"title","bullets","notes","kind":"content"}
Rules: change ONLY what the user asked; apply to both doc and deck when both exist and it makes sense;
keep existing wording elsewhere; cite sources as [n]; set refresh=true if the user wants newer web information."""


class EditorAgent:
    name = "editor"

    def plan(self, ctx: Ctx, instruction: str, doc: DocIR | None, deck: DeckIR | None, sources: list[dict]) -> dict:
        with ctx.step(self.name, "plan_edit", instruction=instruction) as out:
            j = ctx.llm.json(
                "You are a document-editing planner. " + OPS_SPEC,
                f"INSTRUCTION: {instruction}\nCURRENT DOC: {doc.model_dump_json() if doc else None}\n"
                f"CURRENT DECK: {deck.model_dump_json() if deck else None}\n"
                "SOURCES:\n" + "\n".join(f"[{s['id']}] {s['title']}: {s['snippet'][:400]}" for s in sources))
            if j and "ops" in j:
                out["mode"] = "llm"
                return j
            out["mode"] = "fallback"
            return self.heuristic(instruction, doc, deck, sources)

    # Use simple rules when no language model is configured.
    def heuristic(self, msg: str, doc, deck, sources) -> dict:
        m = msg.lower()
        ops, notes = [], []
        scopes = [s for s, x in (("doc", doc), ("deck", deck)) if x]
        refresh = bool(re.search(r"(update|refresh).*(web|latest|current|recent)|latest web", m))
        add = re.search(r"\b(add|include|insert|create|append)\b", m)

        if "executive summary" in m and add:
            pts = self._points(doc, deck)
            if "doc" in scopes:
                ops.append({"scope": "doc", "op": "add", "after": "start",
                            "item": Section(heading="Executive Summary", paragraphs=[" ".join(pts)]).model_dump()})
            if "deck" in scopes:
                ops.append({"scope": "deck", "op": "add", "after": "start",
                            "item": Slide(title="Executive Summary", bullets=[trim_words(p, 16) for p in pts]).model_dump()})
            notes.append("added an Executive Summary")
        if "competitive" in m and add:
            pts = self._competitive(sources)
            if "doc" in scopes:
                ops.append({"scope": "doc", "op": "add", "after": None,
                            "item": Section(heading="Competitive Analysis", bullets=pts).model_dump()})
            if "deck" in scopes:
                ops.append({"scope": "deck", "op": "add", "after": None,
                            "item": Slide(title="Competitive Analysis", bullets=[trim_words(p, 16) for p in pts[:4]]).model_dump()})
            notes.append("added a Competitive Analysis section")
        if re.search(r"\b(concise|shorter|brief|trim|condense|succinct|tighten)\b", m):
            only_deck = re.search(r"\b(presentation|slides?|deck|ppt)\b", m) and not re.search(r"\b(document|report|doc|proposal)\b", m)
            only_doc = re.search(r"\b(document|report|doc|proposal)\b", m) and not re.search(r"\b(presentation|slides?|deck|ppt)\b", m)
            for s in scopes:
                if (only_deck and s != "deck") or (only_doc and s != "doc"):
                    continue
                ops.append({"scope": s, "op": "condense", "max_bullets": 4, "max_words": 14, "max_sentences": 2})
            notes.append("condensed content")
        rm = re.search(r"\b(?:remove|delete|drop)\b (?:the )?(.+?)(?: section| slide|$)", m)
        if rm:
            for s in scopes:
                ops.append({"scope": s, "op": "remove", "match": rm.group(1).strip()})
            notes.append(f"removed '{rm.group(1).strip()}'")
        summary = "; ".join(notes) or ("refreshing with latest research" if refresh else
                                       "I couldn't map that instruction without an LLM. Set OPENROUTER_API_KEY for free-form edits.")
        return {"summary": summary, "refresh": refresh, "ops": ops}

    @staticmethod
    def _points(doc, deck, n=4) -> list[str]:
        pts = []
        if doc:
            for s in doc.sections:
                if s.heading.lower() == "executive summary":
                    continue
                txt = (s.paragraphs or s.bullets or [""])[0]
                if txt:
                    pts.append(trim_words(sentences(txt)[0], 28))
        elif deck:
            for s in deck.slides:
                if s.bullets:
                    pts.append(s.bullets[0])
        return pts[:n]

    @staticmethod
    def _competitive(sources, n=4) -> list[str]:
        rx = re.compile(r"compet|vendor|market share|alternative|versus| vs |rival|leader", re.I)
        picked = [s for s in sources if rx.search(s["snippet"])] or sources
        out = []
        for s in picked[:n]:
            sents = [x for x in sentences(s["snippet"]) if rx.search(x)] or sentences(s["snippet"]) or [s["title"]]
            out.append(f"{trim_words(sents[0], 30)} [{s['id']}]")
        return out or ["No competitive evidence was found in the available sources."]

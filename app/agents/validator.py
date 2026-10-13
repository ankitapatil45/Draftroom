"""Check document structure, slide content, citations, and source grounding."""
import re

from ..models import CITE_RE, DeckIR, DocIR, cited_ids, deck_text, doc_text
from .base import Ctx


class ValidatorAgent:
    name = "validator"

    def run(self, ctx: Ctx, doc: DocIR | None, deck: DeckIR | None, sources: list[dict],
            n_slides: int | None = None) -> dict:
        issues = []
        valid = {s["id"] for s in sources}
        with ctx.step(self.name, "validate") as out:
            if doc:
                if not doc.sections:
                    issues.append(("error", "doc", "document has no sections"))
                for s in doc.sections:
                    if not (s.paragraphs or s.bullets):
                        issues.append(("error", f"doc:{s.heading}", "empty section"))
                    elif sources and not CITE_RE.search(" ".join(s.paragraphs + s.bullets)) \
                            and s.heading.lower() not in ("executive summary", "next steps", "introduction"):
                        issues.append(("warning", f"doc:{s.heading}", "no citation although sources are available"))
            if deck:
                content = [s for s in deck.slides if s.kind == "content"]
                total = 1 + len(content) + (1 if cited_ids(deck=deck) else 0)
                if n_slides and total != n_slides:
                    issues.append(("error", "deck", f"{total} slides rendered, {n_slides} requested"))
                titles = [s.title.lower() for s in content]
                if len(set(titles)) != len(titles):
                    issues.append(("warning", "deck", "duplicate slide titles"))
                for s in content:
                    if len(s.bullets) > 7:
                        issues.append(("warning", f"slide:{s.title}", "more than 7 bullets"))
                    if any(len(CITE_RE.sub('', b).split()) > 24 for b in s.bullets):
                        issues.append(("warning", f"slide:{s.title}", "bullet longer than 24 words"))
            for n in cited_ids(doc, deck) - valid:
                issues.append(("error", "citations", f"[{n}] does not match any source"))
            if ctx.llm.live and sources:
                text = (doc_text(doc) if doc else "") + (deck_text(deck) if deck else "")
                j = ctx.llm.json("You are a strict fact-checker.",
                                 "List claims in CONTENT that the SOURCES do not support. JSON: "
                                 '{"unsupported":[str]}\nCONTENT:\n' + text[:6000] + "\nSOURCES:\n" +
                                 "\n".join(f"[{s['id']}] {s['snippet'][:500]}" for s in sources), 600)
                for c in (j or {}).get("unsupported", [])[:5]:
                    issues.append(("warning", "grounding", str(c)))
            res = {"passed": not any(i[0] == "error" for i in issues),
                   "issues": [{"severity": a, "where": b, "message": c} for a, b, c in issues]}
            out.update(passed=res["passed"], n_issues=len(issues))
            return res

    @staticmethod
    def autofix(doc: DocIR | None, deck: DeckIR | None, sources: list[dict], n_slides: int | None):
        valid = {s["id"] for s in sources}

        def clean(t: str) -> str:
            return re.sub(r"\s{2,}", " ", CITE_RE.sub(lambda m: m.group(0) if int(m.group(1)) in valid else "", t)).strip()

        if doc:
            for s in doc.sections:
                s.paragraphs = [clean(p) for p in s.paragraphs]
                s.bullets = [clean(b) for b in s.bullets]
        if deck:
            for s in deck.slides:
                s.bullets = [clean(b) for b in s.bullets]
            if n_slides:
                content = [s for s in deck.slides if s.kind == "content"]
                has_cites = bool(cited_ids(deck=deck))
                want = n_slides - 1 - (1 if has_cites else 0)
                if len(content) > want > 0:
                    deck.slides = content[:want]

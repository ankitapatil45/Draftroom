"""Read uploaded files and extract style details and reference text."""
from .. import parsers
from .base import Ctx


class TemplateAnalystAgent:
    name = "template_analyst"

    def run(self, ctx: Ctx) -> dict:
        s = ctx.session()
        style = s.get("style", {})
        done = set(s.get("analyzed", []))
        for u in s["uploads"]:
            if u["name"] in done:
                continue
            with ctx.step(self.name, "analyze", file=u["name"], kind=u["kind"]) as out:
                prof = parsers.analyze_any(u["path"])
                prof["file"] = u["name"]
                if u["kind"] in ("docx", "pdf"):
                    style["doc"] = {**prof, "template_path": u["path"] if u["kind"] == "docx" else None}
                elif u["kind"] == "pptx":
                    style["deck"] = {**prof, "template_path": u["path"]}
                else:
                    style.setdefault("reference", []).append(prof)
                text = parsers.extract_text(u["path"])
                style.setdefault("reference_text", {})[u["name"]] = text[:6000]
                done.add(u["name"])
                out["tone"] = prof["tone"]["description"]
                out["headings"] = [h["text"] for h in prof.get("headings", [])][:10]
        ctx.store.update(ctx.sid, style=style, analyzed=sorted(done))
        return style

    @staticmethod
    def template_path(style: dict, which: str):
        t = (style.get(which) or {}).get("template_path")
        return t

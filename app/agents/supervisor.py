"""Coordinate a chat request from planning through file generation."""
import re
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..models import DeckIR, DocIR, Section, Slide, Source, cited_ids
from ..ops import apply_op, sentences, trim_words
from ..render_docx import render_docx
from ..render_pptx import render_pptx
from ..store import SessionStore
from .base import Ctx
from .converter import ConverterAgent
from .deck_writer import DeckWriterAgent
from .doc_writer import DocWriterAgent
from .editor import EditorAgent
from .research import RagAgent, WebResearchAgent
from .template_analyst import TemplateAnalystAgent
from .validator import ValidatorAgent


class RequestState(TypedDict, total=False):
    """Values passed between LangGraph workflow nodes for one chat request."""

    ctx: Ctx
    latest: dict | None
    sources: list[dict]
    doc: DocIR | None
    deck: DeckIR | None
    validation: dict
    response: dict
    slide_count: int | None


def heuristic_plan(msg: str, has_artifacts: bool) -> dict:
    """Choose a basic workflow from common words when no model is configured."""
    m = msg.lower()
    outputs = []
    if re.search(r"\b(ppt|pptx|presentation|slides?|deck|powerpoint)\b", m):
        outputs.append("pptx")
    if re.search(r"\b(doc|docx|document|proposal|report|word|whitepaper)\b", m):
        outputs.append("docx")
    create_request = re.search(r"\b(create|generate|build|draft|prepare|make me|write)\b", m)
    edit_request = re.search(
        r"\b(add|make|update|remove|change|rewrite|shorten|expand|insert|delete|edit|modify|replace|refresh)\b",
        m,
    )
    convert_request = re.search(r"\bconvert\b|\b(turn|transform)\b.*\b(into|to)\b", m)

    if convert_request and has_artifacts:
        intent = "convert"
    elif has_artifacts and edit_request and not create_request:
        intent = "edit"
    elif create_request or (not has_artifacts and re.search(r"research|proposal|presentation", m)):
        intent = "create"
    elif re.match(r"\s*(what|how|who|why|when|which|explain|tell|summar)", m) or m.strip().endswith("?"):
        intent = "answer"
    else:
        intent = "edit" if has_artifacts else "create"
    slide_count = re.search(r"(\d+)[\s-]*slides?", m)
    topic = re.split(
        r"\b(?:and|then)\s+(?:create|generate|build|draft|prepare|write)\b|\busing the same\b",
        msg,
        maxsplit=1,
        flags=re.I,
    )[0]
    topic = re.sub(r"^\s*(please\s+)?(research|create|generate|build|draft|prepare|write)\s+(the\s+)?", "", topic, flags=re.I).strip(" .")
    direction = None
    if convert_request:
        direction = "deck_to_doc" if re.search(r"\b(to|into)\s+(a\s+)?(doc|document|word|report)", m) else "doc_to_deck"
    return {
        "intent": intent,
        "outputs": outputs or ["docx", "pptx"],
        "n_slides": int(slide_count.group(1)) if slide_count else None,
        "topic": topic or msg,
        "needs_web": bool(re.search(r"research|latest|current|recent|trend|news|web|market|20\d{2}", m)),
        "direction": direction,
    }


class Supervisor:
    """Choose the agents for a request and save each finished version."""

    name = "supervisor"

    def __init__(self, store: SessionStore):
        self.store = store
        self.template_analyst = TemplateAnalystAgent()
        self.web_research = WebResearchAgent()
        self.knowledge_search = RagAgent()
        self.document_writer = DocWriterAgent()
        self.presentation_writer = DeckWriterAgent()
        self.validator = ValidatorAgent()
        self.editor = EditorAgent()
        self.converter = ConverterAgent()
        self.graph = self._build_graph()

    def _build_graph(self):
        """Connect the specialist agents into explicit request workflows."""
        graph = StateGraph(RequestState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("analyze_template", self._analyze_template_node)
        graph.add_node("gather_sources", self._gather_sources_node)
        graph.add_node("write_artifacts", self._write_artifacts_node)
        graph.add_node("validate", self._validate_node)
        graph.add_node("commit", self._commit_node)
        graph.add_node("edit", self._edit_node)
        graph.add_node("convert", self._convert_node)
        graph.add_node("answer", self._answer_node)
        graph.add_edge(START, "plan")
        graph.add_conditional_edges(
            "plan", self._route_request,
            {"create": "analyze_template", "edit": "edit", "convert": "convert", "answer": "answer"},
        )
        graph.add_edge("analyze_template", "gather_sources")
        graph.add_edge("gather_sources", "write_artifacts")
        graph.add_edge("write_artifacts", "validate")
        graph.add_edge("validate", "commit")
        for node in ("commit", "edit", "convert", "answer"):
            graph.add_edge(node, END)
        return graph.compile()

    def _plan_node(self, state: RequestState) -> dict:
        ctx = state["ctx"]
        latest = self.store.latest(ctx.sid)
        ctx.plan = self.plan(ctx, latest is not None)
        return {"latest": latest}

    @staticmethod
    def _route_request(state: RequestState) -> str:
        return state["ctx"].plan["intent"]

    def _analyze_template_node(self, state: RequestState) -> dict:
        self.template_analyst.run(state["ctx"])
        return {"ctx": state["ctx"]}

    def _gather_sources_node(self, state: RequestState) -> dict:
        ctx = state["ctx"]
        return {"sources": self._gather(ctx, ctx.plan["topic"])}

    def _write_artifacts_node(self, state: RequestState) -> dict:
        ctx, plan = state["ctx"], state["ctx"].plan
        topic = plan["topic"]
        slide_count = plan.get("n_slides") or 10
        doc = self.document_writer.run(ctx, topic, state["sources"]) if "docx" in plan["outputs"] else None
        deck = self.presentation_writer.run(ctx, topic, state["sources"], slide_count, doc) \
            if "pptx" in plan["outputs"] else None
        return {"doc": doc, "deck": deck, "slide_count": slide_count}

    def _validate_node(self, state: RequestState) -> dict:
        ctx = state["ctx"]
        result = self._validate_and_repair(
            ctx, state.get("doc"), state.get("deck"), state["sources"],
            state.get("slide_count"), ctx.plan["topic"],
        )
        return {"doc": result.pop("doc"), "deck": result.pop("deck"), "validation": result}

    def _commit_node(self, state: RequestState) -> dict:
        ctx = state["ctx"]
        plan = ctx.plan
        response = self._commit(
            ctx, state.get("doc"), state.get("deck"), plan["topic"], state.get("slide_count"),
            note="Initial generation", validation=state["validation"], reply_prefix="Created",
        )
        return {"response": response}

    def _edit_node(self, state: RequestState) -> dict:
        return {"response": self._edit(state["ctx"], state.get("latest"))}

    def _convert_node(self, state: RequestState) -> dict:
        return {"response": self._convert(state["ctx"], state.get("latest"))}

    def _answer_node(self, state: RequestState) -> dict:
        return {"response": self._answer(state["ctx"])}

    # Plan the request and select a graph route.
    def plan(self, ctx: Ctx, has_artifacts: bool) -> dict:
        base = heuristic_plan(ctx.message, has_artifacts)
        with ctx.step(self.name, "plan") as out:
            j = ctx.llm.json(
                "You are the supervisor of a document-generation system. Classify the request.",
                f'Existing artifacts: {has_artifacts}\nMessage: "{ctx.message}"\nJSON: {{"intent":"create|edit|convert|answer",'
                '"outputs":["docx","pptx"],"n_slides":int|null,"topic":str,"needs_web":bool,"direction":"doc_to_deck|deck_to_doc|null"}', 500)
            if j:
                base.update({k: v for k, v in j.items() if v not in (None, "", [])})
            if base.get("intent") not in {"create", "edit", "convert", "answer"}:
                base["intent"] = heuristic_plan(ctx.message, has_artifacts)["intent"]
            if not isinstance(base.get("outputs"), list):
                base["outputs"] = ["docx", "pptx"]
            base["outputs"] = [
                kind for kind in base["outputs"]
                if isinstance(kind, str) and kind in {"docx", "pptx"}
            ]
            if not base["outputs"]:
                base["outputs"] = ["docx", "pptx"]
            if not isinstance(base.get("topic"), str):
                base["topic"] = ctx.message
            if not isinstance(base.get("n_slides"), int) or not 1 <= base["n_slides"] <= 30:
                base["n_slides"] = None
            if not isinstance(base.get("needs_web"), bool):
                base["needs_web"] = heuristic_plan(ctx.message, has_artifacts)["needs_web"]
            if base.get("direction") not in {"doc_to_deck", "deck_to_doc", None}:
                base["direction"] = None
            if base["intent"] in ("edit", "convert") and not has_artifacts:
                base["intent"] = "create"
            out.update(base)
        return base

    # Start a request and invoke the compiled graph.
    def handle(self, sid: str, message: str) -> dict:
        with self.store.locked_session(sid):
            return self._handle_locked(sid, message)

    def _handle_locked(self, sid: str, message: str) -> dict:
        ctx = Ctx(sid=sid, store=self.store, message=message)
        result = self.graph.invoke({"ctx": ctx})
        return result["response"]

    # Gather evidence for a creation workflow.
    def _gather(self, ctx: Ctx, topic: str) -> list[dict]:
        sources = []
        if ctx.plan.get("needs_web", True):
            sources.extend(self.web_research.run(ctx, topic))
        sources.extend(self.knowledge_search.run(ctx, topic))
        return sources

    def _validate_and_repair(self, ctx, doc, deck, sources, slide_count, topic):
        result = self.validator.run(ctx, doc, deck, sources, slide_count)
        errors = [issue["message"] for issue in result["issues"] if issue["severity"] == "error"]
        if errors and ctx.llm.live:
            # Give the writers one chance to fix structural validation errors.
            feedback = "; ".join(errors)
            if doc:
                doc = self.document_writer.run(ctx, topic, sources, feedback=feedback)
            if deck:
                deck = self.presentation_writer.run(
                    ctx, topic, sources, slide_count or 10, doc, feedback=feedback
                )

        self.validator.autofix(doc, deck, sources, slide_count)
        result = self.validator.run(ctx, doc, deck, sources, slide_count)
        result["doc"] = doc
        result["deck"] = deck
        return result

    # 4. Apply edits to the latest structured version.
    def _edit(self, ctx: Ctx, latest: dict) -> dict:
        doc = DocIR(**latest["doc"]) if latest.get("doc") else None
        deck = DeckIR(**latest["deck"]) if latest.get("deck") else None
        topic = latest.get("topic", "")
        sources = ctx.session()["sources"]
        plan = self.editor.plan(ctx, ctx.message, doc, deck, sources)
        changes = []
        if plan.get("refresh"):
            new_sources = self.web_research.run(ctx, topic) + self.knowledge_search.run(ctx, topic)
            sources = ctx.session()["sources"]
            if ctx.llm.live:
                fb = "Update with the NEWEST sources; keep these headings and the same style: " + \
                     str([s.heading for s in doc.sections] if doc else [])
                if doc:
                    doc = self.document_writer.run(ctx, topic, sources, feedback=fb)
                if deck:
                    deck = self.presentation_writer.run(
                        ctx, topic, sources, latest.get("n_slides") or len(deck.slides) + 2, doc, fb
                    )
                changes.append("refreshed with latest research")
            elif new_sources:
                points = [
                    f"{trim_words(sentences(source['snippet'])[0], 26)} [{source['id']}]"
                    for source in new_sources[:4]
                    if source["snippet"]
                ]
                if doc:
                    doc.sections.append(Section(heading="Latest Developments", bullets=points))
                if deck:
                    bullets = [trim_words(point, 16) for point in points]
                    deck.slides.append(Slide(title="Latest Developments", bullets=bullets))
                changes.append("added Latest Developments from fresh research")
        for op in plan.get("ops", []):
            try:
                c = apply_op(doc, deck, op)
            except (KeyError, TypeError, ValueError) as e:
                # Ignore malformed edit operations while keeping valid changes.
                c = ""
                ctx.store.trace(ctx.sid, self.name, "op_failed", {"op": op, "error": str(e)})
            if c:
                changes.append(f"{op.get('scope')}: {c}")
        if not changes:
            return {
                "reply": plan.get("summary") or "No changes were made.",
                "version": latest["number"],
                "files": self._urls(ctx.sid, latest["number"], latest["files"]),
                "changed": False,
            }
        result = self._validate_and_repair(ctx, doc, deck, sources, None, topic)
        doc, deck = result.pop("doc"), result.pop("deck")
        return self._commit(
            ctx,
            doc,
            deck,
            topic,
            latest.get("n_slides"),
            note=ctx.message,
            validation=result,
            reply_prefix="Updated (" + "; ".join(changes) + ")",
            parent=latest["number"],
        )

    # ------------------------------------------------------------------ convert
    def _convert(self, ctx: Ctx, latest: dict) -> dict:
        doc = DocIR(**latest["doc"]) if latest.get("doc") else None
        deck = DeckIR(**latest["deck"]) if latest.get("deck") else None
        direction = ctx.plan.get("direction") or (
            "doc_to_deck" if doc and not deck else "deck_to_doc"
        )
        new_doc, new_deck = self.converter.run(
            ctx, direction, doc, deck, ctx.plan.get("n_slides")
        )
        if new_deck:
            deck = new_deck
        elif new_doc:
            doc = new_doc
        else:
            return {
                "reply": "Nothing to convert from.",
                "version": latest["number"],
                "files": self._urls(ctx.sid, latest["number"], latest["files"]),
                "changed": False,
            }
        sources = ctx.session()["sources"]
        result = self._validate_and_repair(
            ctx, doc, deck, sources, ctx.plan.get("n_slides"), latest.get("topic", "")
        )
        doc, deck = result.pop("doc"), result.pop("deck")
        return self._commit(
            ctx,
            doc,
            deck,
            latest.get("topic", ""),
            ctx.plan.get("n_slides"),
            note=f"Converted ({direction})",
            validation=result,
            reply_prefix="Converted",
            parent=latest["number"],
        )

    # ------------------------------------------------------------------ answer (Q&A with citations)
    def _answer(self, ctx: Ctx) -> dict:
        sources = self.knowledge_search.run(ctx, ctx.message)
        if ctx.plan.get("needs_web"):
            sources += self.web_research.run(ctx, ctx.message)
        if ctx.llm.live and sources:
            evidence = "\n".join(
                f"[{source['id']}] {source['title']}: {source['snippet'][:700]}"
                for source in sources
            )
            answer = ctx.llm.complete(
                "Answer using only the numbered sources; cite as [n]; say if unsupported.",
                f"Q: {ctx.message}\n{evidence}",
            )
        elif sources:
            matches = "\n".join(
                f"- {source['snippet'][:200]} [{source['id']}]"
                for source in sources[:3]
            )
            answer = f"Top matches from the knowledge base:\n{matches}"
        else:
            answer = "I couldn't find anything relevant in the knowledge base or web results."
        return {"reply": answer, "sources": sources, "changed": False}

    # ------------------------------------------------------------------ commit: render + version
    def _urls(self, sid, n, files):
        return {k: f"/api/sessions/{sid}/versions/{n}/download/{k}" for k in files}

    def _commit(self, ctx, doc, deck, topic, n_slides, note, validation, reply_prefix, parent=None):
        session = ctx.session()
        style = session.get("style", {})
        sources = [Source(**source) for source in session["sources"]]
        version_number, version_dir = self.store.new_version_dir(ctx.sid)
        files = {}
        try:
            with ctx.step("renderer", "render", version=version_number) as trace:
                if doc:
                    template = TemplateAnalystAgent.template_path(style, "doc")
                    render_docx(
                        doc,
                        sources,
                        Path(template) if template else None,
                        version_dir / "document.docx",
                    )
                    files["docx"] = "document.docx"
                if deck:
                    template = TemplateAnalystAgent.template_path(style, "deck")
                    render_pptx(
                        deck,
                        sources,
                        Path(template) if template else None,
                        version_dir / "presentation.pptx",
                    )
                    files["pptx"] = "presentation.pptx"
                trace["files"] = files

            used_source_ids = cited_ids(doc, deck)
            state = {
                "parent": parent,
                "note": note,
                "topic": topic,
                "n_slides": n_slides,
                "files": files,
                "doc": doc.model_dump() if doc else None,
                "deck": deck.model_dump() if deck else None,
                "sources": [
                    source for source in session["sources"]
                    if source["id"] in used_source_ids
                ],
                "validation": validation,
                "request": ctx.message,
            }
            self.store.commit_version(ctx.sid, version_number, state)
        except Exception:
            self.store.abandon_version(ctx.sid, version_number)
            raise

        warn = [i for i in validation["issues"] if i["severity"] == "warning"]
        validation_status = "Validation passed" if validation["passed"] else "Validation found problems"
        warning_text = f" with {len(warn)} warning(s)" if warn else ""
        reply = (
            f"{reply_prefix} → version v{version_number} ({', '.join(files)}). "
            f"{validation_status}{warning_text}."
        )
        return {
            "reply": reply,
            "version": version_number,
            "files": self._urls(ctx.sid, version_number, files),
            "validation": validation,
            "sources": state["sources"],
            "plan": ctx.plan,
            "changed": True,
        }

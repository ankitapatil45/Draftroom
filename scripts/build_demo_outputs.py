"""Run the demo workflow and write reviewable artifacts under examples/generated/."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parent.parent

if TYPE_CHECKING:
    from app.store import SessionStore


DEMO_REQUESTS = [
    "Research the latest Generative AI trends and create a proposal and 12-slide presentation using the same tone and style as the uploaded files.",
    "Add an executive summary.",
    "Add a competitive analysis section.",
    "Make the presentation more concise.",
]


def prepare_knowledge_base(get_kb) -> None:
    """Index the included reference material for the demo."""
    knowledge_base = get_kb()
    for path in sorted((ROOT / "examples" / "knowledge_base").iterdir()):
        if path.is_file():
            knowledge_base.ingest_file(path)


def create_demo_session(store: SessionStore, kind_of) -> str:
    """Create a session with the included proposal and slide template."""
    session_id = store.create()
    for path in sorted((ROOT / "examples" / "templates").iterdir()):
        if path.is_file():
            store.save_upload(session_id, path.name, path.read_bytes(), kind_of(path.name))
    return session_id


def write_outputs(store: SessionStore, session_id: str) -> Path:
    """Copy generated versions and the trace to the reviewable output folder."""
    output_dir = ROOT / "examples" / "generated"
    output_dir.mkdir(exist_ok=True)
    generated_name = re.compile(r"v\d+_(document\.docx|presentation\.pptx)")

    for old_file in output_dir.iterdir():
        if old_file.is_file() and (old_file.name == "trace.jsonl" or generated_name.fullmatch(old_file.name)):
            old_file.unlink()

    for version in store.versions(session_id):
        version_dir = store.version_dir(session_id, version["number"])
        for filename in version["files"].values():
            source = version_dir / filename
            destination = output_dir / f"v{version['number']}_{filename}"
            destination.write_bytes(source.read_bytes())

    trace = store.get_trace(session_id)
    trace_path = output_dir / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(record, default=str) + "\n" for record in trace),
        encoding="utf-8",
    )
    return output_dir


def main() -> None:
    """Generate the demo document, deck, revisions, and activity trace."""
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DATA_DIR", str(ROOT / "data" / "demo_runtime"))

    from app.agents.supervisor import Supervisor
    from app.config import settings
    from app.llm import llm
    from app.parsers import kind_of
    from app.rag import get_kb
    from app.store import SessionStore

    if not (settings.tavily_api_key or llm.live):
        settings.enable_web = False

    prepare_knowledge_base(get_kb)
    store = SessionStore()
    session_id = create_demo_session(store, kind_of)
    supervisor = Supervisor(store)

    for request in DEMO_REQUESTS:
        result = supervisor.handle(session_id, request)
        print(f"> {request}\n  {result['reply']}")

    output_dir = write_outputs(store, session_id)
    print("Wrote demo outputs:", ", ".join(sorted(path.name for path in output_dir.iterdir())))


if __name__ == "__main__":
    main()

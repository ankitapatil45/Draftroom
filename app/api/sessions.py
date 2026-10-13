"""Session, upload, chat, and artifact endpoints."""
from pathlib import Path
import subprocess

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..agents.supervisor import Supervisor
from ..config import settings
from ..office import legacy_ppt_to_pptx
from ..parsers import kind_of
from ..store import SessionStore
from .dependencies import get_store, get_supervisor, require_api_key
from .uploads import read_upload

router = APIRouter(
    prefix="/api/sessions",
    tags=["sessions"],
    dependencies=[Depends(require_api_key)],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _session_or_404(store: SessionStore, session_id: str) -> dict:
    try:
        return store.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@router.post("")
def create_session(store: SessionStore = Depends(get_store)):
    return {"session_id": store.create()}


@router.get("/{sid}")
def get_session(sid: str, store: SessionStore = Depends(get_store)):
    session = _session_or_404(store, sid)
    uploads = [{key: upload[key] for key in ("name", "kind", "bytes")} for upload in session["uploads"]]
    return {
        "id": sid,
        "uploads": uploads,
        "versions": store.versions(sid),
        "n_sources": len(session["sources"]),
    }


@router.post("/{sid}/upload")
async def upload_files(
    sid: str,
    files: list[UploadFile] = File(...),
    store: SessionStore = Depends(get_store),
):
    _session_or_404(store, sid)
    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")
    if len(files) > settings.max_upload_files:
        raise HTTPException(status_code=413, detail="too many files in one upload")

    pending = []
    total_bytes = 0
    for file in files:
        try:
            data = await read_upload(file)
            total_bytes += len(data)
            if total_bytes > settings.max_upload_total_mb * 1024 * 1024:
                raise HTTPException(status_code=413, detail="total upload size exceeded")
            filename = file.filename or "upload"
            if Path(filename).suffix.lower() == ".ppt":
                try:
                    data = legacy_ppt_to_pptx(data, filename)
                except (RuntimeError, subprocess.TimeoutExpired) as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                filename = f"{Path(filename).stem}.pptx"
            pending.append((filename, data, kind_of(filename)))
        finally:
            await file.close()
    with store.locked_session(sid):
        uploaded = [store.save_upload(sid, filename, data, kind) for filename, data, kind in pending]

    return {
        "uploaded": [
            {key: record[key] for key in ("name", "kind", "bytes")}
            for record in uploaded
        ]
    }


@router.post("/{sid}/chat")
def chat(
    sid: str,
    body: ChatRequest,
    store: SessionStore = Depends(get_store),
    supervisor: Supervisor = Depends(get_supervisor),
):
    _session_or_404(store, sid)
    with store.locked_session(sid):
        return supervisor.handle(sid, body.message)


@router.get("/{sid}/versions")
def list_versions(sid: str, store: SessionStore = Depends(get_store)):
    _session_or_404(store, sid)
    return store.versions(sid)


@router.get("/{sid}/versions/{number}")
def get_version(sid: str, number: int, store: SessionStore = Depends(get_store)):
    _session_or_404(store, sid)
    try:
        return store.version(sid, number)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc


@router.post("/{sid}/versions/{number}/revert")
def revert_version(sid: str, number: int, store: SessionStore = Depends(get_store)):
    _session_or_404(store, sid)
    with store.locked_session(sid):
        try:
            state = store.revert(sid, number)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="version not found") from exc
        latest = store.latest(sid)
        return {"version": latest["number"], "note": state["note"]}


@router.get("/{sid}/versions/{number}/download/{kind}")
def download_version(
    sid: str,
    number: int,
    kind: str,
    store: SessionStore = Depends(get_store),
):
    _session_or_404(store, sid)
    if kind not in ("docx", "pptx"):
        raise HTTPException(status_code=400, detail="kind must be docx or pptx")
    try:
        state = store.version(sid, number)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc
    if kind not in state["files"]:
        raise HTTPException(status_code=404, detail="artifact not in this version")

    artifact_name = state["files"][kind]
    if Path(artifact_name).name != artifact_name:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = store.version_dir(sid, number) / artifact_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    media_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    return FileResponse(path, media_type=media_types[kind], filename=f"{kind}_v{number}.{kind}")


@router.get("/{sid}/trace")
def get_trace(sid: str, store: SessionStore = Depends(get_store)):
    _session_or_404(store, sid)
    return store.get_trace(sid)


@router.get("/{sid}/sources")
def get_sources(sid: str, store: SessionStore = Depends(get_store)):
    return _session_or_404(store, sid)["sources"]

"""Knowledge-base ingestion and search endpoints."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..config import settings
from ..rag import get_kb
from .dependencies import require_api_key
from .uploads import read_upload

router = APIRouter(
    prefix="/api/kb",
    tags=["knowledge base"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/ingest")
async def ingest_files(files: list[UploadFile] = File(...)):
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
            pending.append((Path(file.filename or "upload").name, data))
        finally:
            await file.close()

    knowledge_base = get_kb()
    chunks_ingested = 0
    for filename, data in pending:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / filename
            path.write_bytes(data)
            chunks_ingested += knowledge_base.ingest_file(path)
    return {"chunks_ingested": chunks_ingested, "backend": knowledge_base.backend}


@router.get("/search")
def search_knowledge_base(
    q: str = Query(min_length=1, max_length=1000),
    k: int = Query(default=5, ge=1, le=10),
):
    return get_kb().search(q, k)

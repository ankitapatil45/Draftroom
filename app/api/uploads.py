"""Shared validation for uploaded files."""
from io import BytesIO
from pathlib import Path
import zipfile

from fastapi import HTTPException, UploadFile

from ..config import settings


def _matches_file_signature(filename: str, data: bytes) -> bool:
    extension = Path(filename).suffix.lower()
    if extension in {".docx", ".pptx"}:
        if not zipfile.is_zipfile(BytesIO(data)):
            return False
        with zipfile.ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            max_unpacked_size = settings.max_upload_mb * 20 * 1024 * 1024
            if any(item.flag_bits & 0x1 for item in members):
                return False
            if sum(item.file_size for item in members) > max_unpacked_size:
                return False
            names = {item.filename for item in members}
        expected = "word/document.xml" if extension == ".docx" else "ppt/presentation.xml"
        return "[Content_Types].xml" in names and expected in names
    if extension == ".pdf":
        return data.startswith(b"%PDF-")
    if extension == ".ppt":
        return data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if extension in {".tif", ".tiff"}:
        return data.startswith((b"II*\x00", b"MM\x00*"))
    return True


async def read_upload(file: UploadFile) -> bytes:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in settings.allowed_ext:
        raise HTTPException(status_code=415, detail=f"unsupported file type {extension}")

    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file too large")
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        valid = _matches_file_signature(filename, data)
    except (OSError, RuntimeError, zipfile.BadZipFile):
        valid = False
    if not valid:
        raise HTTPException(status_code=415, detail="file content does not match its extension")
    return data

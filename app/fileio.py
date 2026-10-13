"""Small atomic-write helpers for local state files."""
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    content = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
    atomic_write(path, content)

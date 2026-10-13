"""Helpers for converting legacy Microsoft Office formats."""
import shutil
import subprocess
import tempfile
from pathlib import Path


def legacy_ppt_to_pptx(data: bytes, filename: str) -> bytes:
    """Convert a binary .ppt upload to editable .pptx with LibreOffice."""
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        raise RuntimeError("Legacy .ppt conversion requires LibreOffice to be installed")

    with tempfile.TemporaryDirectory(prefix="draftroom-ppt-") as temp_dir:
        work_dir = Path(temp_dir)
        source = work_dir / (Path(filename).stem + ".ppt")
        source.write_bytes(data)
        result = subprocess.run(
            [executable, "--headless", "--convert-to", "pptx", "--outdir", str(work_dir), str(source)],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        converted = work_dir / f"{source.stem}.pptx"
        if result.returncode != 0 or not converted.is_file():
            raise RuntimeError("LibreOffice could not convert this .ppt file to .pptx")
        return converted.read_bytes()

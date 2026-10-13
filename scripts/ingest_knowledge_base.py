"""Add files from a folder to the searchable knowledge base."""
import sys
from pathlib import Path


def main() -> None:
    """Ingest each file from the requested folder."""
    project_root = Path(__file__).resolve().parent.parent
    default_folder = project_root / "examples" / "knowledge_base"
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else default_folder
    if not folder.is_dir():
        raise SystemExit(f"Knowledge folder does not exist: {folder}")

    sys.path.insert(0, str(project_root))
    from app.rag import get_kb

    knowledge_base = get_kb()
    chunk_count = sum(
        knowledge_base.ingest_file(path)
        for path in sorted(folder.iterdir())
        if path.is_file()
    )
    print(f"Ingested {chunk_count} chunks into the {knowledge_base.backend} index.")


if __name__ == "__main__":
    main()

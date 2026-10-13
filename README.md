# Draftroom

Draftroom is an interview POC for turning reference files and a request into editable Word documents and PowerPoint presentations. A LangGraph `StateGraph` supervisor routes each request to focused agents for template analysis, research, retrieval, writing, editing, conversion, and validation. OpenRouter provides the model API behind those agents.

## What the POC demonstrates

- DOCX, PDF, legacy PPT, PPTX, and image uploads; legacy PPT is converted to PPTX with LibreOffice. Scanned files use OCR when Tesseract is installed.
- DOCX and PPTX template profiling, including headings, styles, fonts, colors, layouts, and tone cues.
- Web research and retrieval from an example enterprise knowledge base, with source IDs and citations.
- Editable DOCX and PPTX generation, natural-language revisions, and DOCX-to-PPTX / PPTX-to-DOCX conversion.
- SQLite-backed sessions, artifact versions, source records, and agent traces. Generated Office files are stored on disk.
- A browser chat interface and API endpoints documented at `/docs` in development mode.

The generated files reuse template styles and layouts where available; exact visual matching is not guaranteed. This is a single-instance POC: authentication is a shared optional API key, and uploaded files are local. It does not include user accounts, shared object storage, or production operational monitoring.

## Run locally

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
python scripts/ingest_knowledge_base.py
uvicorn app.main:app --reload
```

Open `http://localhost:8000`. SQLite tables are created automatically under `data/` for local use. Alembic migrations are included for a configured PostgreSQL database; set `DATABASE_URL` and run `alembic upgrade head` before starting the app.

For AI-generated planning and writing, add an OpenRouter key to `.env` and choose a model slug available to your account with `OPENROUTER_MODEL`. The default Claude Sonnet model is paid; OpenRouter model pricing and free availability vary, so check your selected model before sending requests. LangGraph is the workflow engine; model calls use OpenRouter's chat completions API. Web search uses Tavily when `TAVILY_API_KEY` is configured and otherwise attempts DDGS. Pinecone is optional; without its key, retrieval uses a local vector index. The local knowledge files in `examples/knowledge_base/` are indexed by the ingestion command. Image descriptions require a vision-capable selected model. OCR for scanned files also needs the Tesseract executable installed on the machine; `pytesseract` alone is not enough. Legacy `.ppt` uploads require the LibreOffice executable; `.pptx` works without it.

## Try the example workflow

1. Upload `examples/templates/Company_Proposal.docx` and `examples/templates/Company_Template.pptx` in the chat UI.
2. Ask: “Research enterprise generative AI trends and create a proposal and a 12-slide presentation using these references.”
3. Review the generated DOCX and PPTX, source list, validation notes, version history, and trace.
4. Ask for a revision, such as “Add an executive summary and make the presentation more concise.”

The bundled outputs and trace are in `examples/generated/`. Rebuild them with `python scripts/build_demo_outputs.py`. That script may use local fallback writing when no model key is set, and disables web research when neither a web search key nor the model is available; check the trace to see which sources and services actually ran.

## Project layout

```text
app/                 API, agents, parsing, retrieval, storage, and file rendering
migrations/          PostgreSQL schema migrations
scripts/             Knowledge ingestion and demo-output commands
examples/            Reference templates, knowledge files, and generated outputs
tests/               Workflow checks (install requirements-dev.txt to run them)
docs/                Architecture, deployment boundary, and file-by-file guide
static/              Browser interface
data/                Local runtime files; excluded from Git
```

See [the file-by-file guide](docs/PYTHON_FILE_GUIDE.md), [architecture](docs/ARCHITECTURE.md), and [deployment boundary](docs/DEPLOYMENT.md) for an interview walkthrough. Do not commit `.env`, API keys, or runtime user files.

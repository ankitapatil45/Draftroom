# Architecture

## Request flow

```text
Browser / API
    -> Supervisor
       -> Template Analyst
       -> Web Research + Knowledge Retrieval
       -> Document Writer / Presentation Writer
       -> Validator
       -> Editor or Converter for follow-up requests
    -> render editable DOCX/PPTX
    -> save files, version, sources, and agent trace
```

The Supervisor classifies a request as create, edit, convert, or answer and routes it through a compiled LangGraph `StateGraph`. The create path has explicit template analysis, source gathering, writing, validation, and commit nodes; the other paths route to the relevant editing, conversion, or answer agents. Agents receive a shared request context and add trace entries as they work. They are Python components in one application, not separate deployed services.

## Main components

| Component | Role |
|---|---|
| API (`app/api/`) | Accepts chat, upload, knowledge, history, source, and download requests. |
| Supervisor (`app/agents/supervisor.py`) | Chooses a workflow, invokes agents, and manages output creation. |
| Template Analyst | Reads document text and visual cues such as DOCX styles, PPTX theme/layouts, and tone. |
| Research + RAG | Gathers web results and retrieves relevant indexed knowledge passages. |
| Writers | Build structured document or slide content and attach source citation IDs. |
| Editor + Converter | Applies natural-language changes or maps content between document and slide structures. |
| Validator | Checks required structure, citations, and output constraints; some checks use the LLM when configured. |
| Renderers | Create editable Office files using template styles/layouts when they can be reused. |
| Store | Records sessions, versions, source metadata, and agent trace in SQLite or PostgreSQL. Files are stored separately under `DATA_DIR`. |

## Content and template handling

Parsers extract text from DOCX, PDF, PPTX, and supported images. Legacy PPT uploads are converted to PPTX before analysis. OCR is used for scanned content when the system Tesseract executable is available; vision descriptions need a configured model. The template analyst builds a compact profile that writers and renderers can use. Reuse of styles and slide layouts improves consistency, but cannot guarantee pixel-identical output for every template.

Writers create structured content before rendering. This gives the editor a stable representation for revisions and conversion, and keeps output as normal editable Word paragraphs and PowerPoint text/shapes. Version records retain the request, parent version, sources, validation results, and trace. Office binaries live on disk, so restoring the database without the matching `DATA_DIR` does not restore the artifacts.

## Evidence and limits

Retrieved sources receive IDs that writers can cite; the UI and API expose source metadata and the trace shows which agent steps ran. Citation checks confirm that IDs refer to registered sources, not that every generated statement is factually correct. Web access, Pinecone, OpenRouter, and OCR depend on their configured services or local tools. Without an OpenRouter key, deterministic fallback paths support a limited demonstration rather than equivalent AI quality.

The POC includes upload size/type checks, filename handling, an optional shared API key, security response headers, and guarded public web fetching. It is intended for a controlled demonstration. It does not provide per-user authorization, multi-tenant isolation, shared file storage, rate limiting, or production monitoring.

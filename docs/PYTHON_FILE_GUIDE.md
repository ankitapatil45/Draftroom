# Python file guide

This guide explains the Python files in plain language. For an interview walkthrough, start with the API, follow the Supervisor, then show how output and history are saved.

## Application entry and settings

| File | Purpose |
|---|---|
| `app/main.py` | Creates the FastAPI application, adds security headers, and connects API routes and the browser UI. |
| `app/config.py` | Reads environment settings such as database URL, API keys, and upload limits. |
| `app/database.py` | Defines the database tables and connects to SQLite or PostgreSQL. |
| `app/models.py` | Defines the Python data shapes for documents, slides, sections, and citations. |
| `app/llm.py` | Sends text and vision requests through OpenRouter; agents use local fallback behavior when no key is configured. |
| `app/web.py` | Runs web searches and retrieves page text. |
| `app/rag.py` | Adds knowledge files to search and retrieves relevant text using local or Pinecone storage. |
| `app/fileio.py` | Writes local files safely so interrupted writes do not leave partial files. |
| `app/office.py` | Converts legacy `.ppt` uploads to `.pptx` using LibreOffice. |
| `app/store.py` | Saves sessions, uploaded-file records, sources, versions, and agent traces; Office files themselves are on disk. |
| `app/ops.py` | Applies requested edits to the structured document and slide data. |
| `app/parsers.py` | Extracts text and style information from Word, PowerPoint, PDF, image, and text files. |
| `app/render_docx.py` | Converts structured document content into an editable Word file. |
| `app/render_pptx.py` | Converts structured slide content into an editable PowerPoint file. |

## API files

| File | Purpose |
|---|---|
| `app/api/dependencies.py` | Shares access to the session store and Supervisor and checks the optional API key. |
| `app/api/health.py` | Reports whether the database and configured services are available. |
| `app/api/sessions.py` | Handles chat requests, uploads, version history, downloads, sources, and traces. |
| `app/api/uploads.py` | Checks upload size, extension, and basic file signature before accepting a file. |
| `app/api/knowledge.py` | Provides endpoints to add files to the knowledge base and search it. |
| `app/api/__init__.py` | Marks the API folder as a Python package. |

## Agent files

| File | Purpose |
|---|---|
| `app/agents/supervisor.py` | Builds a LangGraph workflow that routes requests and runs the specialist agents in order. |
| `app/agents/base.py` | Holds shared request context and records the time and details for each agent step. |
| `app/agents/template_analyst.py` | Reads uploaded references and saves their tone, structure, and style profile. |
| `app/agents/research.py` | Searches the web and knowledge base, then registers results as cited sources. |
| `app/agents/doc_writer.py` | Produces structured document content before rendering. |
| `app/agents/deck_writer.py` | Produces structured slide content before rendering. |
| `app/agents/editor.py` | Turns a natural-language edit into small operations such as add, update, remove, or condense. |
| `app/agents/converter.py` | Maps document sections to slides or slides to document sections. |
| `app/agents/validator.py` | Checks content structure, slide count, and citation references. |
| `app/agents/writing_common.py` | Shares prompt formats and fallback writing helpers used by the writers. |
| `app/agents/__init__.py` | Marks the agents folder as a Python package. |
| `app/__init__.py` | Marks the application folder as a Python package. |

## Database migrations, commands, and checks

| File | Purpose |
|---|---|
| `migrations/env.py` | Connects Alembic to the configured database and application table definitions. |
| `migrations/versions/0001_initial.py` | Creates the initial session, version, and trace tables. |
| `scripts/ingest_knowledge_base.py` | Adds files from a folder to the configured knowledge search backend. |
| `scripts/build_demo_outputs.py` | Runs the demonstration workflow and writes generated documents and trace to `examples/generated/`. |
| `tests/test_pipeline.py` | Checks the create, edit, convert, versioning, citation, and local knowledge-search flows. |

## A simple file-by-file explanation to say aloud

1. “`main.py` starts the API, and `sessions.py` receives a chat request.”
2. “The LangGraph Supervisor in `agents/supervisor.py` routes to a workflow; create requests pass through analysis, evidence gathering, writing, validation, and commit nodes.”
3. “Parsers and research agents collect the template and evidence. Writers create structured content defined by `models.py`.”
4. “The validator checks the content, and the two renderers create editable Word and PowerPoint files.”
5. “The store saves version information and trace records in the database and the actual files on disk.”

The `examples/` directory is demonstration material, not application code. The `data/` directory is runtime storage and is excluded from Git.

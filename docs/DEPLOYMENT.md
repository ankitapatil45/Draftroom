# Running the POC

## Local demonstration

Follow the setup in the root README. The default configuration uses SQLite and local file storage under `data/`. The example knowledge files are indexed with `python scripts/ingest_knowledge_base.py`. Start with one Uvicorn process:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use the browser at `/`, API documentation at `/docs`, and health endpoint at `/api/health`.

## Optional services

- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`: enables model-based planning, writing, editing, validation, and image descriptions through the selected OpenRouter model.
- `OPENROUTER_SITE_URL`, `OPENROUTER_APP_NAME`: identify this app in OpenRouter usage attribution. Visibility defaults to hidden.
- `TAVILY_API_KEY`: preferred web search provider. When absent, the app can use its DuckDuckGo fallback.
- `PINECONE_API_KEY`, `PINECONE_INDEX`: enables hosted vector retrieval; otherwise use the local index.
- `DATABASE_URL`: use PostgreSQL instead of local SQLite. Apply schema with `alembic upgrade head`.
- `API_KEY`: enables a shared `X-API-Key` check for API routes.
- `DATA_DIR`: changes where the database and uploaded/generated files are stored.

Keep real keys in an ignored `.env` file locally or a secret manager on a hosted demo. Never commit credentials.

## Deployment boundary

This project is a single-instance evaluation POC, not a hardened multi-customer service. If hosting it for a reviewer, use a private or access-controlled environment, HTTPS, persistent storage for both the database and `DATA_DIR`, and non-production sample documents. The shared API key is not user identity or per-session authorization. Multi-instance deployment needs shared object storage and additional access controls that are outside this implementation.

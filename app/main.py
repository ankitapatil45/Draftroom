"""Application factory and ASGI entry point."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

from .agents.supervisor import Supervisor
from .api.health import router as health_router
from .api.knowledge import router as knowledge_router
from .api.sessions import router as sessions_router
from .config import settings
from .store import SessionStore


def create_app() -> FastAPI:
    application = FastAPI(
        title="Draftroom API",
        version="1.0.0",
        description="Create, edit, and convert documents and presentations.",
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None if settings.app_env == "production" else "/redoc",
        openapi_url=None if settings.app_env == "production" else "/openapi.json",
    )
    application.state.store = SessionStore()
    application.state.supervisor = Supervisor(application.state.store)

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    application.include_router(health_router)
    application.include_router(sessions_router)
    application.include_router(knowledge_router)
    application.mount(
        "/",
        StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True),
        name="ui",
    )
    return application


app = create_app()

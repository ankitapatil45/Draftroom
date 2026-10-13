"""Unauthenticated liveness endpoint."""
from fastapi import APIRouter
from sqlalchemy import select, literal
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..database import engine
from ..llm import llm

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(select(literal(1)))
        database_ready = True
    except SQLAlchemyError:
        database_ready = False
    return {
        "ok": database_ready,
        "database": "available" if database_ready else "unavailable",
        "llm": llm.live,
        "rag_backend": "pinecone" if settings.pinecone_api_key else "local",
        "web": settings.enable_web,
        "auth_required": bool(settings.api_key),
    }

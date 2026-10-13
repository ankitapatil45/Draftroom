"""Dependencies shared by the API routers."""
import hmac

from fastapi import Header, HTTPException, Request

from ..agents.supervisor import Supervisor
from ..config import settings
from ..store import SessionStore


def require_api_key(x_api_key: str = Header(default="")) -> None:
    configured_key = settings.api_key
    if configured_key and not hmac.compare_digest(x_api_key, configured_key):
        raise HTTPException(status_code=401, detail="invalid API key")


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


def get_supervisor(request: Request) -> Supervisor:
    return request.app.state.supervisor

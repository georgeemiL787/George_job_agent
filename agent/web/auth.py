"""Single-token admin auth for the web UI."""
from __future__ import annotations

import hashlib
import hmac
from urllib.parse import quote

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from agent.config import Settings

ADMIN_COOKIE_NAME = "george_job_agent_admin"
_COOKIE_MESSAGE = b"george-job-agent-admin-session-v1"


def validate_production_security(settings: Settings) -> None:
    if settings.is_production and not settings.web_token:
        raise RuntimeError("WEB_TOKEN is required when ENVIRONMENT=production or RENDER=true")


def _session_value(settings: Settings) -> str:
    return hmac.new(settings.web_token.encode("utf-8"), _COOKIE_MESSAGE, hashlib.sha256).hexdigest()


def is_admin_request(request: Request, settings: Settings) -> bool:
    if not settings.web_token:
        return False
    auth = request.headers.get("authorization", "")
    expected_bearer = f"Bearer {settings.web_token}"
    if hmac.compare_digest(auth, expected_bearer):
        return True
    cookie = request.cookies.get(ADMIN_COOKIE_NAME, "")
    return hmac.compare_digest(cookie, _session_value(settings))


def require_admin(request: Request, settings: Settings) -> None:
    if is_admin_request(request, settings):
        return
    if not settings.web_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WEB_TOKEN is not configured",
        )
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")


def admin_redirect(request: Request) -> RedirectResponse:
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    return RedirectResponse(f"/login?next={quote(path)}", status_code=status.HTTP_303_SEE_OTHER)


def set_admin_cookie(response: Response, settings: Settings) -> None:
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        _session_value(settings),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def clear_admin_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        ADMIN_COOKIE_NAME,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )

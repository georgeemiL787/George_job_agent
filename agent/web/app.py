"""FastAPI app for the local web UI."""
from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent.config import Settings, get_settings
from agent.web import jobs
from agent.web.auth import (
    admin_redirect,
    clear_admin_cookie,
    is_admin_request,
    require_admin,
    set_admin_cookie,
    validate_production_security,
)
from agent.web.scheduler_manager import WebScheduler, read_schedule
from agent.web.schemas import (
    LoginRequest,
    MarkAppliedRequest,
    RoleCreate,
    RunRequest,
    ScheduleConfig,
)
from agent.web.services import (
    add_manual_role,
    approve_role,
    get_role,
    list_roles,
    mark_role_applied,
    package_role_service,
    resolve_artifact,
    status_payload,
    sync_master_service,
    tail_log,
    tailor_role,
)
from agent.workspace_seed import seed_workspace

_scheduler: WebScheduler | None = None
_WEB_DIR = Path(__file__).parent
_STATIC_DIR = _WEB_DIR / "static"
_ADMIN_DIR = _WEB_DIR / "admin_static"
_TEMPLATES = Jinja2Templates(directory=str(_WEB_DIR / "templates"))


def _settings() -> Settings:
    return get_settings()


def require_admin_dependency(
    request: Request,
    settings: Settings = Depends(_settings),
) -> None:
    require_admin(request, settings)


def _admin_file(request: Request, settings: Settings, filename: str):
    if not is_admin_request(request, settings):
        return admin_redirect(request)
    return FileResponse(_ADMIN_DIR / filename)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    settings = get_settings()
    validate_production_security(settings)
    seed_workspace(settings)
    _scheduler = WebScheduler(settings)
    _scheduler.start()
    try:
        yield
    finally:
        _scheduler.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="George Job Agent",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/")
    def root(request: Request, settings: Settings = Depends(_settings)):
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="public.html",
            context={
                "public_email": settings.public_email,
                "public_linkedin": settings.public_linkedin,
                "public_github": settings.public_github,
            },
        )

    @app.get("/cv/george-emil-sadek.pdf")
    def public_cv(settings: Settings = Depends(_settings)):
        path = settings.public_cv_file.resolve()
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Public CV not found")
        return FileResponse(
            path,
            media_type="application/pdf",
            filename="george-emil-sadek-cv.pdf",
        )

    @app.get("/login")
    def login(request: Request):
        return _TEMPLATES.TemplateResponse(request=request, name="login.html")

    @app.post("/api/auth/login")
    def api_login(
        body: LoginRequest,
        response: Response,
        settings: Settings = Depends(_settings),
    ):
        if not settings.web_token:
            raise HTTPException(status_code=503, detail="WEB_TOKEN is not configured")
        if not hmac.compare_digest(body.token, settings.web_token):
            raise HTTPException(status_code=401, detail="Invalid admin token")
        set_admin_cookie(response, settings)
        return {"ok": True}

    @app.post("/api/auth/logout")
    def api_logout(response: Response, settings: Settings = Depends(_settings)):
        clear_admin_cookie(response, settings)
        return {"ok": True}

    @app.get("/admin")
    def admin_index(request: Request, settings: Settings = Depends(_settings)):
        return _admin_file(request, settings, "index.html")

    @app.get("/admin/roles")
    def admin_roles(request: Request, settings: Settings = Depends(_settings)):
        return _admin_file(request, settings, "roles.html")

    @app.get("/admin/role")
    def admin_role(request: Request, settings: Settings = Depends(_settings)):
        return _admin_file(request, settings, "role.html")

    @app.get("/admin/add-role")
    def admin_add_role(request: Request, settings: Settings = Depends(_settings)):
        return _admin_file(request, settings, "add-role.html")

    @app.get("/admin/app.js")
    def admin_app_js(request: Request, settings: Settings = Depends(_settings)):
        return _admin_file(request, settings, "app.js")

    @app.get("/api/status", dependencies=[Depends(require_admin_dependency)])
    def api_status(
        drafts_only: bool = Query(False),
        settings: Settings = Depends(_settings),
    ):
        return status_payload(settings, drafts_only=drafts_only)

    @app.get("/api/jobs/current", dependencies=[Depends(require_admin_dependency)])
    def api_job(settings: Settings = Depends(_settings)):
        return jobs.current_state(settings)

    @app.post("/api/run", status_code=202, dependencies=[Depends(require_admin_dependency)])
    def api_run(
        request_body: RunRequest | None = None,
        dry_run: bool | None = Query(None),
        settings: Settings = Depends(_settings),
    ):
        dry = bool(dry_run) if dry_run is not None else bool(request_body and request_body.dry_run)
        if not jobs.start_run(dry_run=dry, manual=True, settings=settings):
            raise HTTPException(status_code=409, detail="A run is already active")
        return jobs.current_state(settings)

    @app.get("/api/schedule", dependencies=[Depends(require_admin_dependency)])
    def api_schedule():
        if _scheduler:
            return _scheduler.status()
        return read_schedule()

    @app.put("/api/schedule", dependencies=[Depends(require_admin_dependency)])
    def api_update_schedule(config: ScheduleConfig):
        try:
            if not _scheduler:
                raise RuntimeError("Scheduler is not running")
            return _scheduler.apply(config.model_dump())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/api/logs/tail", dependencies=[Depends(require_admin_dependency)])
    def api_logs_tail(lines: int = Query(200, ge=1, le=1000), settings: Settings = Depends(_settings)):
        return {"lines": tail_log(settings, lines)}

    @app.get("/api/roles", dependencies=[Depends(require_admin_dependency)])
    def api_roles(
        drafts_only: bool = Query(False),
        include_applied: bool = Query(False),
        settings: Settings = Depends(_settings),
    ):
        return {
            "roles": list_roles(
                settings,
                drafts_only=drafts_only,
                include_applied=include_applied,
            )
        }

    @app.get("/api/roles/{slug}", dependencies=[Depends(require_admin_dependency)])
    def api_role(slug: str, settings: Settings = Depends(_settings)):
        role = get_role(settings, slug)
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        return role

    @app.post("/api/roles", dependencies=[Depends(require_admin_dependency)])
    def api_add_role(body: RoleCreate, settings: Settings = Depends(_settings)):
        return add_manual_role(settings, body.model_dump())

    @app.post("/api/roles/{slug}/tailor", dependencies=[Depends(require_admin_dependency)])
    def api_tailor(slug: str, settings: Settings = Depends(_settings)):
        try:
            return tailor_role(settings, slug)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/api/roles/{slug}/approve", dependencies=[Depends(require_admin_dependency)])
    def api_approve(slug: str, settings: Settings = Depends(_settings)):
        try:
            approve_role(settings, slug)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/api/roles/{slug}/package", dependencies=[Depends(require_admin_dependency)])
    def api_package(slug: str, settings: Settings = Depends(_settings)):
        try:
            return package_role_service(settings, slug)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/api/roles/{slug}/mark-applied", dependencies=[Depends(require_admin_dependency)])
    def api_mark_applied(
        slug: str,
        body: MarkAppliedRequest | None = None,
        settings: Settings = Depends(_settings),
    ):
        try:
            mark_role_applied(settings, slug, body.date if body else "")
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.get("/api/files/{slug}/{filename}", dependencies=[Depends(require_admin_dependency)])
    def api_file(slug: str, filename: str, settings: Settings = Depends(_settings)):
        try:
            path = resolve_artifact(settings, slug, filename)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="File not found") from e
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return FileResponse(path)

    @app.post("/api/sync-master", dependencies=[Depends(require_admin_dependency)])
    def api_sync_master(settings: Settings = Depends(_settings)):
        return sync_master_service(settings)

    @app.get("/healthz")
    def healthz():
        return Response("ok", media_type="text/plain")

    return app


app = create_app()

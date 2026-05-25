"""FastAPI app for the local web UI."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agent.config import Settings, get_settings
from agent.web import jobs
from agent.web.scheduler_manager import WebScheduler, read_schedule
from agent.web.schemas import MarkAppliedRequest, RoleCreate, RunRequest, ScheduleConfig
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

_scheduler: WebScheduler | None = None


def _settings() -> Settings:
    return get_settings()


def require_token(request: Request, settings: Settings = Depends(_settings)) -> None:
    if not settings.web_token:
        return
    expected = f"Bearer {settings.web_token}"
    if request.headers.get("authorization") != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    settings = get_settings()
    _scheduler = WebScheduler(settings)
    _scheduler.start()
    try:
        yield
    finally:
        _scheduler.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="George Job Agent", lifespan=lifespan)
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def root():
        return RedirectResponse("/static/index.html")

    @app.get("/api/status")
    def api_status(
        drafts_only: bool = Query(False),
        settings: Settings = Depends(_settings),
    ):
        return status_payload(settings, drafts_only=drafts_only)

    @app.get("/api/jobs/current")
    def api_job(settings: Settings = Depends(_settings)):
        return jobs.current_state(settings)

    @app.post("/api/run", status_code=202, dependencies=[Depends(require_token)])
    def api_run(
        request_body: RunRequest | None = None,
        dry_run: bool | None = Query(None),
        settings: Settings = Depends(_settings),
    ):
        dry = bool(dry_run) if dry_run is not None else bool(request_body and request_body.dry_run)
        if not jobs.start_run(dry_run=dry, manual=True, settings=settings):
            raise HTTPException(status_code=409, detail="A run is already active")
        return jobs.current_state(settings)

    @app.get("/api/schedule")
    def api_schedule():
        if _scheduler:
            return _scheduler.status()
        return read_schedule()

    @app.put("/api/schedule", dependencies=[Depends(require_token)])
    def api_update_schedule(config: ScheduleConfig):
        try:
            if not _scheduler:
                raise RuntimeError("Scheduler is not running")
            return _scheduler.apply(config.model_dump())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/api/logs/tail")
    def api_logs_tail(lines: int = Query(200, ge=1, le=1000), settings: Settings = Depends(_settings)):
        return {"lines": tail_log(settings, lines)}

    @app.get("/api/roles")
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

    @app.get("/api/roles/{slug}")
    def api_role(slug: str, settings: Settings = Depends(_settings)):
        role = get_role(settings, slug)
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        return role

    @app.post("/api/roles", dependencies=[Depends(require_token)])
    def api_add_role(body: RoleCreate, settings: Settings = Depends(_settings)):
        return add_manual_role(settings, body.model_dump())

    @app.post("/api/roles/{slug}/tailor", dependencies=[Depends(require_token)])
    def api_tailor(slug: str, settings: Settings = Depends(_settings)):
        try:
            return tailor_role(settings, slug)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/api/roles/{slug}/approve", dependencies=[Depends(require_token)])
    def api_approve(slug: str, settings: Settings = Depends(_settings)):
        try:
            approve_role(settings, slug)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/api/roles/{slug}/package", dependencies=[Depends(require_token)])
    def api_package(slug: str, settings: Settings = Depends(_settings)):
        try:
            return package_role_service(settings, slug)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/api/roles/{slug}/mark-applied", dependencies=[Depends(require_token)])
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

    @app.get("/api/files/{slug}/{filename}", dependencies=[Depends(require_token)])
    def api_file(slug: str, filename: str, settings: Settings = Depends(_settings)):
        try:
            path = resolve_artifact(settings, slug, filename)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="File not found") from e
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return FileResponse(path)

    @app.post("/api/sync-master", dependencies=[Depends(require_token)])
    def api_sync_master(settings: Settings = Depends(_settings)):
        return sync_master_service(settings)

    @app.get("/healthz")
    def healthz():
        return Response("ok", media_type="text/plain")

    return app


app = create_app()

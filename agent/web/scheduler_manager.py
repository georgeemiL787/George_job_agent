"""Web-controlled APScheduler manager."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from agent.config import Settings, get_settings
from agent.web.jobs import run_agent_once, start_run

SCHEDULE_JOB_ID = "job_search_refresh"
ALLOWED_INTERVALS = {1, 2, 4}


def _schedule_path(settings: Settings) -> Path:
    return settings.config_path / "schedule.json"


def default_schedule(settings: Settings) -> dict[str, Any]:
    interval = settings.schedule_interval_hours
    if interval not in ALLOWED_INTERVALS:
        interval = 4
    return {"enabled": False, "interval_hours": interval}


def read_schedule(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    path = _schedule_path(settings)
    if not path.exists():
        return default_schedule(settings)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_schedule(settings)
    enabled = bool(data.get("enabled", False))
    interval = int(data.get("interval_hours", settings.schedule_interval_hours))
    if interval not in ALLOWED_INTERVALS:
        interval = 4
    return {"enabled": enabled, "interval_hours": interval}


def write_schedule(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    interval = int(data.get("interval_hours", 4))
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("interval_hours must be one of 1, 2, or 4")
    config = {"enabled": bool(data.get("enabled", False)), "interval_hours": interval}
    path = _schedule_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


class WebScheduler:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.scheduler = BackgroundScheduler(timezone=pytz.timezone(self.settings.timezone))

    def start(self) -> None:
        self.apply(read_schedule(self.settings))
        self.scheduler.start(paused=False)
        logger.info("Web scheduler started")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Web scheduler stopped")

    def apply(self, config: dict[str, Any]) -> dict[str, Any]:
        config = write_schedule(config, self.settings)
        if self.scheduler.get_job(SCHEDULE_JOB_ID):
            self.scheduler.remove_job(SCHEDULE_JOB_ID)

        if config["enabled"]:
            self.scheduler.add_job(
                func=self._scheduled_run,
                trigger="interval",
                hours=config["interval_hours"],
                id=SCHEDULE_JOB_ID,
                replace_existing=True,
            )
        return self.status()

    def _scheduled_run(self) -> None:
        started = start_run(dry_run=False, manual=False, settings=self.settings)
        if not started:
            logger.warning("Scheduled run skipped because another run is active")

    def status(self) -> dict[str, Any]:
        config = read_schedule(self.settings)
        job = self.scheduler.get_job(SCHEDULE_JOB_ID) if self.scheduler.running else None
        next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
        return {**config, "next_run_time": next_run}


def start_blocking_scheduler() -> None:
    settings = get_settings()
    tz = pytz.timezone(settings.timezone)
    scheduler = BlockingScheduler(timezone=tz)
    config = read_schedule(settings)
    interval = config["interval_hours"]

    scheduler.add_job(
        func=lambda: run_agent_once(manual=False, dry_run=False, settings=settings),
        trigger="interval",
        hours=interval,
        id=SCHEDULE_JOB_ID,
        replace_existing=True,
    )

    logger.info(f"Scheduler started: every {interval}h in {settings.timezone}")
    logger.info("Running initial cycle immediately on scheduler start...")
    run_agent_once(manual=False, dry_run=False, settings=settings)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")

"""Long-running run lock and background job state."""
from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass
from typing import Any

import pytz
from loguru import logger

from agent.config import Settings, get_settings
from agent.observability.run_report import load_latest_run_report


@dataclass
class JobState:
    status: str = "idle"
    started_at: str | None = None
    dry_run: bool = False
    error: str | None = None


_run_lock = threading.Lock()
_state_lock = threading.Lock()
_state = JobState()


def _now(settings: Settings) -> str:
    return dt.datetime.now(tz=pytz.timezone(settings.timezone)).isoformat()


def run_agent_once(*, manual: bool, dry_run: bool, settings: Settings | None = None) -> bool:
    """Run the orchestrator synchronously if no other run is active."""
    settings = settings or get_settings()
    if not _run_lock.acquire(blocking=False):
        logger.warning("Agent run skipped because another run is already active")
        return False

    with _state_lock:
        _state.status = "running"
        _state.started_at = _now(settings)
        _state.dry_run = dry_run
        _state.error = None

    try:
        from agent.orchestrator import run

        run(manual=manual, dry_run=dry_run)
        with _state_lock:
            _state.status = "idle"
        return True
    except Exception as e:
        logger.exception(f"Agent run failed: {e}")
        with _state_lock:
            _state.status = "error"
            _state.error = str(e)
        return True
    finally:
        _run_lock.release()


def start_run(
    *,
    dry_run: bool,
    manual: bool = True,
    settings: Settings | None = None,
) -> bool:
    """Start a background run. Returns False when already busy."""
    settings = settings or get_settings()
    if _run_lock.locked():
        return False

    thread = threading.Thread(
        target=run_agent_once,
        kwargs={"manual": manual, "dry_run": dry_run, "settings": settings},
        daemon=True,
    )
    thread.start()
    return True


def current_state(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    with _state_lock:
        data = {
            "status": _state.status,
            "started_at": _state.started_at,
            "dry_run": _state.dry_run,
            "error": _state.error,
        }
    data["latest_run"] = load_latest_run_report(settings)
    return data

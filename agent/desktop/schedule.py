"""Schedule configuration for the desktop app."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.config import Settings

ALLOWED_INTERVALS = {1, 2, 4}


def _schedule_path(settings: Settings) -> Path:
    return settings.config_path / "schedule.json"


def default_schedule(settings: Settings) -> dict[str, Any]:
    interval = settings.schedule_interval_hours
    if interval not in ALLOWED_INTERVALS:
        interval = 4
    return {"enabled": False, "interval_hours": interval}


def read_schedule(settings: Settings) -> dict[str, Any]:
    path = _schedule_path(settings)
    if not path.exists():
        return default_schedule(settings)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_schedule(settings)
    interval = int(data.get("interval_hours", settings.schedule_interval_hours))
    if interval not in ALLOWED_INTERVALS:
        interval = 4
    return {"enabled": bool(data.get("enabled", False)), "interval_hours": interval}


def write_schedule(settings: Settings, enabled: bool, interval_hours: int) -> dict[str, Any]:
    if interval_hours not in ALLOWED_INTERVALS:
        raise ValueError("interval_hours must be one of 1, 2, or 4")
    config = {"enabled": enabled, "interval_hours": interval_hours}
    path = _schedule_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config

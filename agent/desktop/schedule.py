"""Schedule configuration for the desktop app."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.config import Settings

ALLOWED_INTERVALS = (1, 2, 4, 6, 8, 12, 24)


def _schedule_path(settings: Settings) -> Path:
    return settings.config_path / "schedule.json"


def _normalize_interval(hours: int) -> int:
    if hours in ALLOWED_INTERVALS:
        return hours
    return min(ALLOWED_INTERVALS, key=lambda x: abs(x - hours))


def default_schedule(settings: Settings) -> dict[str, Any]:
    interval = _normalize_interval(settings.schedule_interval_hours)
    return {"enabled": False, "interval_hours": interval}


def read_schedule(settings: Settings) -> dict[str, Any]:
    path = _schedule_path(settings)
    if not path.exists():
        return default_schedule(settings)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_schedule(settings)
    interval = _normalize_interval(int(data.get("interval_hours", settings.schedule_interval_hours)))
    return {"enabled": bool(data.get("enabled", False)), "interval_hours": interval}


def write_schedule(settings: Settings, enabled: bool, interval_hours: int) -> dict[str, Any]:
    interval_hours = _normalize_interval(interval_hours)
    config = {"enabled": enabled, "interval_hours": interval_hours}
    path = _schedule_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config

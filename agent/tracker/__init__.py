"""Tracker backend factory."""
from __future__ import annotations

from agent.config import Settings
from agent.tracker.sql import SqlTracker

_tracker_cache: dict[str, SqlTracker] = {}


def get_tracker(settings: Settings) -> SqlTracker:
    """Return the live tracker backend, cached per database URL."""
    key = settings.database_url
    if key not in _tracker_cache:
        tracker = SqlTracker(settings)
        tracker.load_or_create()
        _tracker_cache[key] = tracker
    return _tracker_cache[key]


def reset_tracker_cache() -> None:
    """Invalidate the tracker cache (used when database_url changes at runtime)."""
    _tracker_cache.clear()

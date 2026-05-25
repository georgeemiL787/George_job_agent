"""Tracker backend factory."""
from __future__ import annotations

from agent.config import Settings
from agent.tracker.sql import SqlTracker


def get_tracker(settings: Settings) -> SqlTracker:
    """Return the live tracker backend."""
    return SqlTracker(settings)

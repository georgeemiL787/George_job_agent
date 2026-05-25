"""Tracker backend factory."""
from __future__ import annotations

from agent.config import Settings
from agent.tracker.postgres import PostgresTracker


def get_tracker(settings: Settings) -> PostgresTracker:
    """Return the live tracker backend."""
    return PostgresTracker(settings)

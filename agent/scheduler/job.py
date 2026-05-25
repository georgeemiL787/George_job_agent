"""APScheduler 4-hour job loop — Africa/Cairo timezone."""
from __future__ import annotations

from loguru import logger


def run_sync() -> None:
    """Synchronous wrapper around the async orchestrator run."""
    from agent.web.jobs import run_agent_once

    if not run_agent_once(manual=False, dry_run=False):
        logger.warning("Scheduled run skipped because another run is active")


def start_scheduler() -> None:
    """Start the blocking scheduler."""
    try:
        from agent.web.scheduler_manager import start_blocking_scheduler
    except ImportError:
        logger.error("Scheduler dependencies missing. Run: pip install -r requirements.txt")
        return

    start_blocking_scheduler()

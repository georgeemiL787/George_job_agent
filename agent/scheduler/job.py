"""APScheduler job loop for CLI-only scheduling."""
from __future__ import annotations

import threading

from loguru import logger

_run_lock = threading.Lock()


def run_sync() -> None:
    """Synchronous scheduled run with overlap protection."""
    from agent.orchestrator import run

    if not _run_lock.acquire(blocking=False):
        logger.warning("Scheduled run skipped because another run is active")
        return
    try:
        run(manual=False, dry_run=False)
    finally:
        _run_lock.release()


def start_scheduler() -> None:
    """Start the blocking scheduler."""
    try:
        import pytz
        from apscheduler.schedulers.blocking import BlockingScheduler

        from agent.config import get_settings
    except ImportError:
        logger.error("Scheduler dependencies missing. Run: pip install -r requirements.txt")
        return

    settings = get_settings()
    scheduler = BlockingScheduler(timezone=pytz.timezone(settings.timezone))
    scheduler.add_job(
        func=run_sync,
        trigger="interval",
        hours=settings.schedule_interval_hours,
        id="job_search_refresh",
        replace_existing=True,
    )

    logger.info(f"Scheduler started: every {settings.schedule_interval_hours}h in {settings.timezone}")
    logger.info("Running initial cycle immediately on scheduler start...")
    run_sync()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")

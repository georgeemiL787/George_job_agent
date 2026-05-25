"""APScheduler 4-hour job loop — Africa/Cairo timezone."""
from __future__ import annotations

from loguru import logger


def run_sync() -> None:
    """Synchronous wrapper around the async orchestrator run."""
    try:
        from agent.orchestrator import run
        run(manual=False, dry_run=False)
    except Exception as e:
        logger.error(f"Scheduled run failed: {e}")


def start_scheduler() -> None:
    """Start the blocking scheduler."""
    try:
        import pytz
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        logger.error("APScheduler or pytz not installed. Run: pip install apscheduler pytz")
        return

    from agent.config import get_settings
    settings = get_settings()
    tz = pytz.timezone(settings.timezone)

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        func=run_sync,
        trigger="interval",
        hours=settings.schedule_interval_hours,
        id="job_search_refresh",
        replace_existing=True,
    )

    logger.info(
        f"Scheduler started: every {settings.schedule_interval_hours}h in {settings.timezone}"
    )

    # Run once immediately on startup
    logger.info("Running initial cycle immediately on scheduler start...")
    run_sync()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")

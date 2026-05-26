"""Single entry point for full agent runs (CLI, desktop, scheduler)."""
from __future__ import annotations

from agent.config import get_settings
from agent.orchestrator import run as orchestrator_run
from agent.run_control import RunOptions, RunStatus, get_coordinator


def validate_run_settings() -> list[str]:
    settings = get_settings()
    warnings: list[str] = []
    if not settings.openrouter_api_key.strip():
        warnings.append("OPENROUTER_API_KEY is empty — scoring and tailoring will fail.")
    return warnings


def run_agent(
    *,
    manual: bool = True,
    dry_run: bool = False,
    options: RunOptions | None = None,
) -> RunStatus:
    """Run the pipeline. Returns final run status."""
    opts = options or RunOptions(dry_run=dry_run)
    opts.dry_run = dry_run
    for msg in validate_run_settings():
        if not dry_run:
            import warnings as _warnings

            _warnings.warn(msg)
    try:
        orchestrator_run(manual=manual, dry_run=dry_run, options=opts)
    except Exception:
        return get_coordinator().get_status() or RunStatus.FAILED
    return get_coordinator().get_status() or RunStatus.COMPLETE


def run_agent_exit_code(
    *,
    manual: bool = True,
    dry_run: bool = False,
    options: RunOptions | None = None,
) -> int:
    status = run_agent(manual=manual, dry_run=dry_run, options=options)
    if status in (RunStatus.FAILED, RunStatus.CANCELLED):
        return 1
    return 0

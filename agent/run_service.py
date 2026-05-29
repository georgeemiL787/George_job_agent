"""Single entry point for full agent runs (CLI, desktop, scheduler)."""
from __future__ import annotations

import warnings
from pathlib import Path

from agent.config import Settings, get_settings
from agent.orchestrator import run as orchestrator_run
from agent.run_control import RunOptions, RunStatus, get_coordinator


def _file_has_text(path: Path) -> bool:
    try:
        return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def run_preflight_errors(
    settings: Settings | None = None,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Return blocking setup problems for a scoring/tailoring run."""
    settings = settings or get_settings()
    errors: list[str] = []

    if not settings.openrouter_api_key.strip():
        errors.append("OpenRouter API key is missing. Add OPENROUTER_API_KEY in Settings or .env.")
    if not settings.database_url.strip():
        errors.append("DATABASE_URL is missing. Save Settings once to create the local tracker path.")

    profile_path = settings.memory_path / "job-search-profile.md"
    if not _file_has_text(profile_path):
        errors.append(
            f"Candidate profile is missing: {profile_path}. "
            "Create this file from your real profile/CV before scoring."
        )

    if not dry_run:
        cv_facts_path = settings.memory_path / "cv-facts.md"
        legacy_cv_notes_path = settings.memory_path / "cv-notes.md"
        if not _file_has_text(cv_facts_path) and not _file_has_text(legacy_cv_notes_path):
            errors.append(
                f"CV facts are missing: {cv_facts_path}. "
                "Create this file with truthful CV facts before tailoring artifacts."
            )

    return errors


def validate_run_settings(*, dry_run: bool = False) -> list[str]:
    return run_preflight_errors(dry_run=dry_run)


def run_agent(
    *,
    manual: bool = True,
    dry_run: bool = False,
    options: RunOptions | None = None,
) -> RunStatus:
    """Run the pipeline. Returns final run status."""
    opts = options or RunOptions(dry_run=dry_run)
    opts.dry_run = dry_run
    errors = validate_run_settings(dry_run=dry_run)
    if errors:
        for msg in errors:
            warnings.warn(msg)
        return RunStatus.FAILED
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

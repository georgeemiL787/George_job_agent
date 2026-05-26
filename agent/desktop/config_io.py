"""Read and update the local .env file for the desktop app."""
from __future__ import annotations

import json
from pathlib import Path

from agent.config import Settings

DESKTOP_ENV_KEYS = [
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "SCORING_MODEL",
    "CV_MODEL",
    "LETTER_MODEL",
    "FALLBACK_MODEL",
    "WORKSPACE_DIR",
    "CV_VARIATIONS_DIR",
    "LATEX_BIN",
    "LOG_LEVEL",
    "TIMEZONE",
    "SCHEDULE_INTERVAL_HOURS",
    "MAX_ROLES_PER_RUN",
    "MIN_SCORE_TO_TAILOR",
    "DATABASE_URL",
    "NOTIFY_ENABLED",
    "NOTIFY_MIN_TIER",
    "NOTIFY_WEBHOOK_URL",
]


def sqlite_url_for_workspace(workspace_dir: str) -> str:
    return f"sqlite:///{Path(workspace_dir).as_posix()}/tracker/job_agent.db"


def desktop_defaults(settings: Settings | None = None) -> dict[str, str]:
    settings = settings or Settings()
    workspace_dir = str(settings.workspace_dir or "workspace")
    return {
        "OPENROUTER_API_KEY": settings.openrouter_api_key,
        "OPENROUTER_BASE_URL": settings.openrouter_base_url,
        "SCORING_MODEL": settings.scoring_model,
        "CV_MODEL": settings.cv_model,
        "LETTER_MODEL": settings.letter_model,
        "FALLBACK_MODEL": settings.fallback_model,
        "WORKSPACE_DIR": workspace_dir,
        "CV_VARIATIONS_DIR": settings.cv_variations_dir,
        "LATEX_BIN": settings.latex_bin,
        "LOG_LEVEL": settings.log_level,
        "TIMEZONE": settings.timezone,
        "SCHEDULE_INTERVAL_HOURS": str(settings.schedule_interval_hours),
        "MAX_ROLES_PER_RUN": str(settings.max_roles_per_run),
        "MIN_SCORE_TO_TAILOR": str(settings.min_score_to_tailor),
        "DATABASE_URL": settings.database_url or sqlite_url_for_workspace(workspace_dir),
        "NOTIFY_ENABLED": str(settings.notify_enabled).lower(),
        "NOTIFY_MIN_TIER": settings.notify_min_tier,
        "NOTIFY_WEBHOOK_URL": settings.notify_webhook_url,
    }


def read_env(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env_values(updates: dict[str, str], path: Path = Path(".env")) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key, _value = line.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)

    missing = [key for key in DESKTOP_ENV_KEYS if key in updates and key not in seen]
    if missing and output and output[-1].strip():
        output.append("")
    for key in missing:
        output.append(f"{key}={updates[key]}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def setup_is_missing(settings: Settings) -> bool:
    return not settings.openrouter_api_key.strip() or not settings.database_url.strip()


def run_sources_path(settings: Settings) -> Path:
    return settings.config_path / "run_sources.json"


def read_run_sources(settings: Settings) -> set[str] | None:
    path = run_sources_path(settings)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = data.get("sources")
        if isinstance(sources, list):
            return {str(s).lower() for s in sources if s}
    except (json.JSONDecodeError, OSError):
        return None
    return None


def write_run_sources(settings: Settings, sources: set[str]) -> Path:
    path = run_sources_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"sources": sorted(sources)}, indent=2),
        encoding="utf-8",
    )
    return path

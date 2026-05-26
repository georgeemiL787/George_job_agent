"""Agent configuration using pydantic-settings + .env."""
from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenRouter (OpenAI-compatible)
    openrouter_api_key: str = ""
    openrouter_api_key_pool: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model selection — reliable free OpenRouter models (May 2026)
    scoring_model: str = "openai/gpt-oss-120b:free"
    cv_model: str = "openai/gpt-oss-120b:free"
    letter_model: str = "openai/gpt-oss-20b:free"
    fallback_model: str = "openai/gpt-oss-20b:free"
    # Ordered comma-separated pool of models tried in rotation after primary+fallback both fail
    model_pool: str = "openai/gpt-oss-120b:free,openai/gpt-oss-20b:free,nvidia/nemotron-3-super-120b-a12b:free"

    # Workspace
    workspace_dir: str = "workspace"
    cv_variations_dir: str = "cv_variations"
    latex_bin: str = "pdflatex"
    log_level: str = "INFO"

    # Agent behaviour
    timezone: str = "Africa/Cairo"
    schedule_interval_hours: int = 4
    max_roles_per_run: int = 20
    min_score_to_tailor: int = 60
    persist_dry_run_scores: bool = True

    # Scoring rate limits
    scoring_model_fast: str = ""
    scorer_max_retries: int = 5
    scorer_backoff_base_seconds: float = 2.0
    scorer_delay_seconds: float = 2.0  # throttle burst: 2s between scoring calls
    run_report_retention_days: int = 30

    # Tailorer retry / back-off (mirrors scorer logic)
    tailor_max_retries: int = 4
    tailor_backoff_base_seconds: float = 3.0

    # Letter writer retry / back-off
    letter_max_retries: int = 3
    letter_backoff_base_seconds: float = 3.0

    # Inter-call delay between tailor/letter LLM calls (seconds)
    # Prevents burst-firing all artifact requests at once after scoring
    tailor_delay_seconds: float = 3.0

    # Source controls
    enabled_sources: str = "wuzzuf,linkedin,bayt"
    skip_slow_sources: bool = True
    enable_indeed: bool = False
    scraper_timeout_seconds: int = 25
    max_scoring_candidates: int = 30
    prefilter_min_score: int = 40
    fast_run_max_scoring_candidates: int = 20
    deep_run_max_scoring_candidates: int = 40
    linkedin_posted_within_hours: int = 168

    # Notifications (optional)
    notify_enabled: bool = False
    notify_min_tier: str = "strong"
    notify_webhook_url: str = ""

    # Local database
    database_url: str = "sqlite:///workspace/tracker/job_agent.db"

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Derived paths (not from .env)
    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_dir)

    @property
    def memory_path(self) -> Path:
        return self.workspace_path / "memory"

    @property
    def cv_tailored_path(self) -> Path:
        return self.workspace_path / "cv" / "tailored"

    @property
    def cv_master_path(self) -> Path:
        return self.workspace_path / "cv" / "master"

    @property
    def cover_letters_path(self) -> Path:
        return self.workspace_path / "cover_letters"

    @property
    def tracker_path(self) -> Path:
        return self.workspace_path / "tracker"

    @property
    def logs_path(self) -> Path:
        return self.workspace_path / "logs"

    @property
    def packages_path(self) -> Path:
        return self.workspace_path / "packages"

    @property
    def config_path(self) -> Path:
        return self.workspace_path / "config"

    @property
    def runs_log_path(self) -> Path:
        return self.logs_path / "runs"

    @property
    def cv_variations_path(self) -> Path:
        """Historical CV PDF archive bundled at the repo root."""
        p = Path(self.cv_variations_dir)
        if p.is_absolute():
            return p
        return self.repo_root / self.cv_variations_dir

    def enabled_source_set(self) -> set[str]:
        return {s.strip().lower() for s in self.enabled_sources.split(",") if s.strip()}

    def get_api_keys(self) -> list[str]:
        """Return the primary key followed by any keys in the pool."""
        keys = []
        if self.openrouter_api_key.strip():
            keys.append(self.openrouter_api_key.strip())
        for k in self.openrouter_api_key_pool.split(","):
            if k.strip() and k.strip() not in keys:
                keys.append(k.strip())
        return keys

    @property
    def repo_root(self) -> Path:
        import sys

        # When running as a PyInstaller bundle, __file__ lives inside the
        # read-only _internal directory.  Use _MEIPASS (the bundle root) so
        # seed_workspace can locate the bundled workspace/memory files.
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(__file__).resolve().parents[1]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

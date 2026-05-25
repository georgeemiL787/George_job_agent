"""Agent configuration using pydantic-settings + .env"""
import os
from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenRouter (OpenAI-compatible)
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model selection
    scoring_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    cv_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    letter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    fallback_model: str = "openai/gpt-oss-120b:free"

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

    # Notifications (optional)
    notify_enabled: bool = False
    notify_min_tier: str = "strong"
    notify_webhook_url: str = ""

    # Database / web app
    database_url: str = ""
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    web_token: str = ""
    environment: str = "local"

    # Public profile
    public_cv_path: str = "cv_variations/george_emil_aiml_engineer_cv.pdf"
    public_email: str = ""
    public_linkedin: str = ""
    public_github: str = ""

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

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

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @property
    def public_cv_file(self) -> Path:
        p = Path(self.public_cv_path)
        if p.is_absolute():
            return p
        return self.repo_root / p

    @property
    def is_production(self) -> bool:
        env = self.environment.lower()
        return env in {"production", "prod"} or os.getenv("RENDER", "").lower() == "true"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

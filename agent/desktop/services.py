"""Desktop service layer over the agent backend modules."""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent.artifacts import build_cv_artifact
from agent.config import Settings
from agent.cv.master_cv import load_master_cv_facts
from agent.manual_role import process_manual_role
from agent.observability.run_report import load_latest_run_report
from agent.orchestrator import run as run_agent
from agent.package_role import package_role
from agent.search.base import JobListing
from agent.search.linkedin_import import RoleDraft, draft_to_listing
from agent.sync_master import sync_master_tex
from agent.tracker import get_tracker
from agent.tracker.import_export import export_tracker, import_tracker
from agent.tracker.models import RoleRecord
from agent.workspace_seed import seed_workspace

WORKSPACE_DIRS = [
    "memory",
    "tracker",
    "logs",
    "logs/runs",
    "cv/tailored",
    "cv/master",
    "cover_letters",
    "packages",
    "roles",
    "config",
]


def artifact_paths(settings: Settings, slug: str) -> dict[str, Path]:
    return {
        "cv_tex": settings.cv_tailored_path / f"{slug}.tex",
        "cv_pdf": settings.cv_tailored_path / f"{slug}.pdf",
        "letter_tex": settings.cover_letters_path / f"{slug}_letter.tex",
        "letter_pdf": settings.cover_letters_path / f"{slug}_letter.pdf",
    }


def role_payload(role: RoleRecord, settings: Settings) -> dict[str, Any]:
    payload = role.to_api_dict()
    payload["artifacts"] = {name: path.exists() for name, path in artifact_paths(settings, role.slug).items()}
    return payload


def ensure_workspace(settings: Settings) -> None:
    for item in WORKSPACE_DIRS:
        (settings.workspace_path / item).mkdir(parents=True, exist_ok=True)


def initialize_local_tracker(settings: Settings) -> dict[str, Any]:
    ensure_workspace(settings)
    seeded = seed_workspace(settings)
    tracker = get_tracker(settings)
    tracker.load_or_create()
    imported = 0
    if not tracker.get_all_slugs():
        workbook = settings.tracker_path / "george_emil_job_tracker.xlsx"
        if workbook.exists():
            imported = import_tracker(settings, workbook)
    return {"database_url": settings.database_url, "imported": imported, "seeded": len(seeded)}


class DesktopService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def initialize(self) -> dict[str, Any]:
        return initialize_local_tracker(self.settings)

    def list_roles(
        self,
        *,
        drafts_only: bool = False,
        include_applied: bool = False,
    ) -> list[dict[str, Any]]:
        tracker = get_tracker(self.settings)
        tracker.load_or_create()
        return [
            role_payload(role, self.settings)
            for role in tracker.list_pipeline_rows(
                drafts_only=drafts_only,
                include_applied=include_applied,
            )
        ]

    def get_role(self, slug: str) -> dict[str, Any] | None:
        tracker = get_tracker(self.settings)
        tracker.load_or_create()
        role = tracker.get_row_by_slug(slug)
        return role_payload(role, self.settings) if role else None

    def run_cycle(self, *, dry_run: bool = False) -> None:
        run_agent(manual=True, dry_run=dry_run)

    def add_manual_role(self, body: dict[str, str]) -> dict[str, Any]:
        draft = RoleDraft(
            title=body["title"],
            company=body["company"],
            location=body.get("location", ""),
            apply_url=body["apply_url"],
            description=body["description"],
            source=body.get("source", "manual"),
        )
        listing = draft_to_listing(draft)
        result = process_manual_role(listing, self.settings)
        role = self.get_role(listing.slug)
        return {"score": result, "role": role}

    def tailor_role(self, slug: str) -> dict[str, str | None]:
        tracker = get_tracker(self.settings)
        tracker.load_or_create()
        role = tracker.get_row_by_slug(slug)
        if not role:
            raise ValueError(f"Slug not found: {slug}")

        listing = JobListing(
            title=role.title,
            company=role.company,
            location=role.location,
            source=role.source or "manual",
            apply_url=role.apply_url,
            slug=slug,
        )
        score_result = {
            "score": role.score or self.settings.min_score_to_tailor,
            "tier": role.tier or "medium",
            "role_family": role.role_family or "adjacent",
            "key_matches": [],
            "fit_summary": role.fit_summary,
        }
        master_facts = load_master_cv_facts(
            self.settings,
            role_family=score_result["role_family"],
            company=listing.company,
        )
        artifact = build_cv_artifact(listing, score_result, master_facts, self.settings)
        if not artifact.ok:
            raise ValueError("; ".join(artifact.errors or ["CV tailoring failed"]))
        tracker.mark_cv_ready(slug)
        tracker.mark_draft(slug)
        tracker.save()
        return {
            "tex_path": str(artifact.tex_path) if artifact.tex_path else None,
            "pdf_path": str(artifact.pdf_path) if artifact.pdf_path else None,
        }

    def approve_role(self, slug: str) -> None:
        tracker = get_tracker(self.settings)
        tracker.load_or_create()
        if not tracker.get_row_by_slug(slug):
            raise ValueError(f"Slug not found: {slug}")
        tracker.mark_ready_for_apply(slug)
        tracker.save()

    def mark_applied(self, slug: str, date: str = "") -> None:
        tracker = get_tracker(self.settings)
        tracker.load_or_create()
        if not tracker.get_row_by_slug(slug):
            raise ValueError(f"Slug not found: {slug}")
        tracker.mark_applied(slug, date or dt.date.today().isoformat())
        tracker.save()

    def package_role(self, slug: str) -> Path:
        return package_role(slug, self.settings)

    def export_tracker(self, output: Path | None = None) -> Path:
        return export_tracker(self.settings, output)

    def import_tracker(self, source: Path | None = None) -> int:
        return import_tracker(self.settings, source)

    def latest_run_report(self) -> dict | None:
        return load_latest_run_report(self.settings)

    def tail_log(self, lines: int = 300) -> list[str]:
        path = self.settings.logs_path / "agent.log"
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]

    def sync_master(self) -> Path:
        return sync_master_tex(self.settings)


def _playwright_install_cmd() -> list[str]:
    """Return the command list to run 'playwright install chromium'.

    When running as a PyInstaller bundle sys.executable is the frozen .exe,
    so 'sys.executable -m playwright' does not work.  Instead we invoke the
    playwright.cmd CLI that is bundled inside _internal/playwright/driver/.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        driver = Path(sys._MEIPASS) / "playwright" / "driver" / "playwright.cmd"
        return [str(driver), "install", "chromium"]
    return [sys.executable, "-m", "playwright", "install", "chromium"]


def check_playwright() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True, "Playwright Chromium is installed."
    except Exception as exc:
        return False, f"Playwright Chromium is not ready: {exc}"


def install_playwright_chromium() -> str:
    result = subprocess.run(
        _playwright_install_cmd(),
        check=False,
        capture_output=True,
        text=True,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    if result.returncode != 0:
        raise RuntimeError(output or "Playwright Chromium installation failed.")
    return output or "Playwright Chromium installed."


def check_pdflatex(latex_bin: str) -> tuple[bool, str]:
    path = shutil.which(latex_bin)
    if path:
        return True, f"LaTeX found: {path}"
    return False, ".tex-only mode is active because pdflatex was not found."

"""Desktop service layer over the agent backend modules."""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent.artifacts import build_cv_artifact, build_letter_artifact
from agent.scrape_health import run_scrape_health
from agent.config import Settings
from agent.cv.master_cv import load_master_cv_facts
from agent.desktop.config_io import setup_is_missing
from agent.desktop.role_context import listing_from_role, score_result_from_role
from agent.tailor_gates import should_tailor_cv, should_tailor_letter
from agent.manual_role import process_manual_role
from agent.observability.run_report import load_active_run_report, load_latest_run_report
from agent.package_role import package_role
from agent.run_control import RunOptions, get_coordinator
from agent.run_service import run_agent
from agent.search.base import JobListing
from agent.search.linkedin_import import RoleDraft, draft_to_listing
from agent.sync_master import sync_master_tex
from agent.tracker import get_tracker
from agent.tracker.import_export import export_tracker, import_tracker
from agent.tracker.models import RoleRecord, effective_score, format_added_date
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
    payload["display_score"] = effective_score(role)
    payload["added_date"] = format_added_date(role)
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

    def run_cycle(
        self,
        *,
        dry_run: bool = False,
        mode: str = "fast",
        sources: set[str] | None = None,
    ) -> None:
        run_agent(
            manual=True,
            dry_run=dry_run,
            options=RunOptions(mode=mode, dry_run=dry_run, sources=sources),
        )

    def retry_failed_scores(self, limit: int = 20) -> int:
        from agent.memory.store import MemoryStore
        from agent.scoring.payload import score_payload_json
        from agent.scoring.scorer import score_listing

        tracker = get_tracker(self.settings)
        tracker.load_or_create()
        profile = MemoryStore(self.settings).load_profile()
        failed = tracker.list_by_scoring_status("failed", limit=limit)
        seen = {role.slug for role in failed}
        for role in tracker.list_pipeline_rows(include_applied=True):
            if len(failed) >= limit:
                break
            if role.slug in seen:
                continue
            if role.scoring_status == "failed":
                continue
            if role.score > 0 or role.tier != "skip":
                continue
            if role.scoring_status == "skipped":
                continue
            failed.append(role)
            seen.add(role.slug)
        retried = 0
        for role in failed[:limit]:
            listing = listing_from_role(role, self.settings)
            result = score_listing(listing, profile, self.settings)
            if result.get("scoring_failed"):
                tracker.set_role_scoring(
                    role.slug,
                    scoring_status="failed",
                    failure_reason=result.get("failure_reason", ""),
                )
                continue
            tracker.upsert_role(
                listing,
                result,
                scoring_status="skipped" if result["tier"] == "skip" else "scored",
                failure_reason="",
                score_payload=score_payload_json(result),
            )
            retried += 1
        tracker.rerank()
        tracker.save()
        return retried

    def cancel_run(self) -> None:
        get_coordinator().request_cancel()

    def is_run_active(self) -> bool:
        return get_coordinator().is_active()

    def get_run_progress(self) -> dict[str, Any]:
        return get_coordinator().get_progress().to_dict()

    def get_run_events(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in get_coordinator().get_events()]

    def get_run_options(self) -> dict[str, Any]:
        opts = get_coordinator().get_options()
        if not opts:
            return {}
        return {
            "mode": opts.mode,
            "dry_run": opts.dry_run,
            "sources": sorted(opts.sources) if opts.sources else None,
        }

    def active_run_report(self) -> dict | None:
        return load_active_run_report(self.settings)

    def resolved_config_summary(self) -> str:
        s = self.settings
        lines = [
            f"Enabled sources: {', '.join(sorted(s.enabled_source_set()))}",
            f"Skip slow (fast): {s.skip_slow_sources}",
            f"Indeed default: {s.enable_indeed}",
            f"Max scoring candidates: {s.max_scoring_candidates}",
            f"Fast cap: {s.fast_run_max_scoring_candidates} | Deep cap: {s.deep_run_max_scoring_candidates}",
            f"Scoring model: {s.scoring_model}",
        ]
        if s.scoring_model_fast:
            lines.append(f"Fast scoring model: {s.scoring_model_fast}")
        return "\n".join(lines)

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

    def scrape_health_report(self, *, mode: str = "fast") -> str:
        stats = run_scrape_health(self.settings, mode=mode)
        lines = [f"Scraper health ({mode} mode):", ""]
        for name, row in stats.items():
            msg = row.get("message") or row.get("error") or ""
            lines.append(f"{name}: {row.get('count', 0)} [{row.get('status', '?')}] {msg}".strip())
        return "\n".join(lines) if lines else "No sources enabled."

    def tailor_role(self, slug: str, *, force: bool = False) -> dict[str, str | None]:
        if setup_is_missing(self.settings):
            raise ValueError(
                "OpenRouter API key is not configured. Open Settings and add your OPENROUTER_API_KEY."
            )

        tracker = get_tracker(self.settings)
        tracker.load_or_create()
        role = tracker.get_row_by_slug(slug)
        if not role:
            raise ValueError(f"Role not found: {slug}")

        score_result = score_result_from_role(role)
        score = int(score_result.get("score") or 0)
        if not force and not should_tailor_cv(score, self.settings):
            raise ValueError(
                f"Score {score} is below the minimum {self.settings.min_score_to_tailor} required to tailor a CV. "
                "Use Force tailor to override."
            )

        listing = listing_from_role(role, self.settings)
        if len((listing.description or "").strip()) < 80:
            raise ValueError(
                "Not enough job description text for tailoring. Re-run search to fetch descriptions, "
                "or add a role manually with a full description."
            )

        try:
            master_facts = load_master_cv_facts(
                self.settings,
                role_family=str(score_result.get("role_family") or ""),
                company=listing.company,
            )
        except FileNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        artifact = build_cv_artifact(listing, score_result, master_facts, self.settings)
        if not artifact.ok:
            detail = "; ".join(artifact.errors or ["CV tailoring failed"])
            raise ValueError(detail)

        tracker.mark_cv_ready(slug)
        tracker.mark_draft(slug)
        tracker.set_artifact_status(slug, "cv_done")
        tracker.save()
        return {
            "tex_path": str(artifact.tex_path) if artifact.tex_path else None,
            "pdf_path": str(artifact.pdf_path) if artifact.pdf_path else None,
        }

    def tailor_letter_role(self, slug: str) -> dict[str, str | None]:
        if setup_is_missing(self.settings):
            raise ValueError(
                "OpenRouter API key is not configured. Open Settings and add your OPENROUTER_API_KEY."
            )

        tracker = get_tracker(self.settings)
        tracker.load_or_create()
        role = tracker.get_row_by_slug(slug)
        if not role:
            raise ValueError(f"Role not found: {slug}")

        score_result = score_result_from_role(role)
        tier = str(score_result.get("tier") or "")
        if not should_tailor_letter(tier):
            raise ValueError(f"Tier '{tier}' is not eligible for cover letter generation.")

        listing = listing_from_role(role, self.settings)
        try:
            master_facts = load_master_cv_facts(
                self.settings,
                role_family=str(score_result.get("role_family") or ""),
                company=listing.company,
            )
        except FileNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        artifact = build_letter_artifact(listing, score_result, master_facts, self.settings)
        if not artifact.ok:
            detail = "; ".join(artifact.errors or ["Cover letter generation failed"])
            raise ValueError(detail)

        tracker.mark_letter_ready(slug)
        tracker.mark_draft(slug)
        tracker.set_artifact_status(slug, "letter_done")
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
    bundled node.exe with the playwright cli.js script.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        driver_dir = Path(sys._MEIPASS) / "playwright" / "driver"
        node_exe = driver_dir / "node.exe"
        cli_js = driver_dir / "package" / "cli.js"
        return [str(node_exe), str(cli_js), "install", "chromium"]
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
    return (
        False,
        f"'{latex_bin}' not found on PATH. "
        "Install MiKTeX (winget install MiKTeX.MiKTeX) or TeX Live to enable PDF output. "
        "The agent will still produce .tex files in tex-only mode.",
    )


def install_miktex() -> str:
    """Install MiKTeX via winget (Windows package manager)."""
    winget = shutil.which("winget")
    if not winget:
        raise RuntimeError(
            "winget is not available on this system. "
            "Download MiKTeX manually from https://miktex.org/download"
        )
    result = subprocess.run(
        [
            winget,
            "install",
            "--id", "MiKTeX.MiKTeX",
            "--silent",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    if result.returncode not in (0, -1978335189):  # 0 = success, -1978335189 = already installed
        raise RuntimeError(output or "MiKTeX installation failed.")
    return output or "MiKTeX installed. Restart the app and check setup again."


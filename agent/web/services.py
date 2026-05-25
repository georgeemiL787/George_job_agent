"""Service helpers shared by web routes."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from agent.artifacts import build_cv_artifact
from agent.config import Settings
from agent.cv.master_cv import load_master_cv_facts
from agent.manual_role import process_manual_role
from agent.observability.run_report import load_latest_run_report
from agent.package_role import package_role
from agent.search.base import JobListing
from agent.search.linkedin_import import RoleDraft, draft_to_listing
from agent.sync_master import sync_master_tex
from agent.tracker import get_tracker
from agent.tracker.models import RoleRecord


def artifact_paths(settings: Settings, slug: str) -> dict[str, Path]:
    return {
        "cv_tex": settings.cv_tailored_path / f"{slug}.tex",
        "cv_pdf": settings.cv_tailored_path / f"{slug}.pdf",
        "letter_tex": settings.cover_letters_path / f"{slug}_letter.tex",
        "letter_pdf": settings.cover_letters_path / f"{slug}_letter.pdf",
    }


def role_payload(role: RoleRecord, settings: Settings) -> dict[str, Any]:
    payload = role.to_api_dict()
    paths = artifact_paths(settings, role.slug)
    payload["artifacts"] = {name: path.exists() for name, path in paths.items()}
    return payload


def list_roles(
    settings: Settings,
    *,
    drafts_only: bool = False,
    include_applied: bool = False,
) -> list[dict[str, Any]]:
    tracker = get_tracker(settings)
    tracker.load_or_create()
    return [
        role_payload(role, settings)
        for role in tracker.list_pipeline_rows(
            drafts_only=drafts_only,
            include_applied=include_applied,
        )
    ]


def _normalize_latest_run(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return report
    normalized = dict(report)
    scrapers = {}
    for name, stat in (report.get("scrapers") or {}).items():
        item = dict(stat or {})
        count = int(item.get("count") or 0)
        error = item.get("error")
        item["status"] = item.get("status") or ("error" if error else ("ok" if count else "empty"))
        item["message"] = item.get("message") or error or ""
        scrapers[name] = item
    normalized["scrapers"] = scrapers
    return normalized


def status_payload(settings: Settings, *, drafts_only: bool = False) -> dict[str, Any]:
    return {
        "latest_run": _normalize_latest_run(load_latest_run_report(settings)),
        "roles": list_roles(settings, drafts_only=drafts_only, include_applied=False),
    }


def get_role(settings: Settings, slug: str) -> dict[str, Any] | None:
    tracker = get_tracker(settings)
    tracker.load_or_create()
    role = tracker.get_row_by_slug(slug)
    return role_payload(role, settings) if role else None


def add_manual_role(settings: Settings, body: dict[str, Any]) -> dict[str, Any]:
    draft = RoleDraft(
        title=body["title"],
        company=body["company"],
        location=body.get("location", ""),
        apply_url=body["apply_url"],
        description=body["description"],
        source=body.get("source", "manual"),
    )
    listing = draft_to_listing(draft)
    result = process_manual_role(listing, settings)
    role = get_role(settings, listing.slug)
    return {"score": result, "role": role}


def tailor_role(settings: Settings, slug: str) -> dict[str, Any]:
    tracker = get_tracker(settings)
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
        "score": role.score or settings.min_score_to_tailor,
        "tier": role.tier or "medium",
        "role_family": role.role_family or "adjacent",
        "key_matches": [],
        "fit_summary": role.fit_summary,
    }
    master_facts = load_master_cv_facts(
        settings,
        role_family=score_result["role_family"],
        company=listing.company,
    )
    cv_art = build_cv_artifact(listing, score_result, master_facts, settings)
    if not cv_art.ok:
        raise ValueError("; ".join(cv_art.errors or ["CV tailoring failed"]))
    tracker.mark_cv_ready(slug)
    tracker.mark_draft(slug)
    tracker.save()
    return {
        "tex_path": str(cv_art.tex_path) if cv_art.tex_path else None,
        "pdf_path": str(cv_art.pdf_path) if cv_art.pdf_path else None,
    }


def approve_role(settings: Settings, slug: str) -> None:
    tracker = get_tracker(settings)
    tracker.load_or_create()
    if not tracker.get_row_by_slug(slug):
        raise ValueError(f"Slug not found: {slug}")
    tracker.mark_ready_for_apply(slug)
    tracker.save()


def mark_role_applied(settings: Settings, slug: str, date: str = "") -> None:
    tracker = get_tracker(settings)
    tracker.load_or_create()
    if not tracker.get_row_by_slug(slug):
        raise ValueError(f"Slug not found: {slug}")
    tracker.mark_applied(slug, date or dt.date.today().isoformat())
    tracker.save()


def package_role_service(settings: Settings, slug: str) -> dict[str, str]:
    out = package_role(slug, settings)
    return {"path": str(out)}


def sync_master_service(settings: Settings) -> dict[str, str]:
    return {"path": str(sync_master_tex(settings))}


def resolve_artifact(settings: Settings, slug: str, filename: str) -> Path:
    tracker = get_tracker(settings)
    tracker.load_or_create()
    if not tracker.get_row_by_slug(slug):
        raise ValueError(f"Slug not found: {slug}")
    allowed = {
        "cv.pdf": settings.cv_tailored_path / f"{slug}.pdf",
        "cv.tex": settings.cv_tailored_path / f"{slug}.tex",
        "letter.pdf": settings.cover_letters_path / f"{slug}_letter.pdf",
        "letter.tex": settings.cover_letters_path / f"{slug}_letter.tex",
    }
    if filename not in allowed:
        raise ValueError("Unknown artifact")
    path = allowed[filename].resolve()
    roots = [settings.cv_tailored_path.resolve(), settings.cover_letters_path.resolve()]
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError("Invalid path")
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def tail_log(settings: Settings, lines: int) -> list[str]:
    path = settings.logs_path / "agent.log"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]

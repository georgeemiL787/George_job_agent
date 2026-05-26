"""Build JobListing and score payloads from tracker rows for desktop actions."""
from __future__ import annotations

import json

from loguru import logger

from agent.config import Settings
from agent.search.base import BaseScraper, JobListing
from agent.search.registry import build_scraper_registry
from agent.tracker.models import RoleRecord, effective_score


def _normalize_source(source: str) -> str:
    s = (source or "manual").lower()
    if s == "linkedin":
        return "linkedin_jobs"
    return s


def score_result_from_role(role: RoleRecord) -> dict:
    """Reconstruct scorer output from tracker columns."""
    ats = [k.strip() for k in (role.ats_keywords or "").split(",") if k.strip()]
    result: dict = {
        "score": effective_score(role),
        "tier": role.tier or "medium",
        "role_family": role.role_family or "adjacent",
        "fit_summary": role.fit_summary or "",
        "key_matches": [],
        "gaps": [],
        "ats_keywords": ats,
    }
    if not role.score_payload:
        return result
    try:
        payload = json.loads(role.score_payload)
    except json.JSONDecodeError:
        return result
    if not isinstance(payload, dict):
        return result
    for key in (
        "score",
        "key_matches",
        "gaps",
        "reasoning",
        "ats_keywords",
        "fit_summary",
        "tier",
        "role_family",
    ):
        if key in payload and payload[key] is not None:
            result[key] = payload[key]
    if not result["ats_keywords"] and ats:
        result["ats_keywords"] = ats
    return result


def _description_from_payload(role: RoleRecord) -> str:
    raw = role.source_payload or ""
    if not raw.strip():
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("description") or "")


def _synthetic_description(role: RoleRecord) -> str:
    lines = [
        f"Title: {role.title}",
        f"Company: {role.company}",
        f"Location: {role.location}",
    ]
    if role.fit_summary:
        lines.append(f"Role fit summary: {role.fit_summary}")
    if role.ats_keywords:
        lines.append(f"ATS keywords: {role.ats_keywords}")
    return "\n".join(lines)


def fetch_role_description(listing: JobListing, settings: Settings) -> str:
    """Try to load a job description via the source scraper."""
    source = _normalize_source(listing.source)
    if not listing.apply_url or source == "manual":
        return ""
    registry = build_scraper_registry()
    cls = registry.get(source)
    if not cls:
        return ""
    scraper: BaseScraper = cls()
    try:
        text = scraper.fetch_description(listing, timeout_seconds=settings.scraper_timeout_seconds)
        return (text or "").strip()
    except Exception as exc:
        logger.warning(f"Could not fetch description for {listing.slug} ({source}): {exc}")
        return ""


def listing_from_role(role: RoleRecord, settings: Settings) -> JobListing:
    listing = JobListing(
        title=role.title,
        company=role.company,
        location=role.location,
        source=role.source or "manual",
        apply_url=role.apply_url,
        slug=role.slug,
    )
    description = _description_from_payload(role)
    if not description:
        description = fetch_role_description(listing, settings)
    if not description:
        description = _synthetic_description(role)
    listing.description = description
    return listing

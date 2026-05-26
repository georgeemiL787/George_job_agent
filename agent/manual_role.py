"""Score, track, and tailor a manually added role (LinkedIn or other)."""
from __future__ import annotations

from loguru import logger

from agent.artifacts import build_cv_artifact, build_letter_artifact
from agent.config import Settings
from agent.cv.master_cv import load_master_cv_facts
from agent.memory.store import MemoryStore
from agent.scoring.scorer import score_listing
from agent.search.base import JobListing
from agent.tailor_gates import should_tailor_cv, should_tailor_letter
from agent.scoring.payload import score_payload_json
from agent.tracker import get_tracker


def process_manual_role(listing: JobListing, settings: Settings) -> dict:
    """Score, upsert tracker, tailor CV/letter when thresholds match."""
    memory = MemoryStore(settings)
    profile = memory.load_profile()

    logger.info(f"Scoring manual role: {listing.company} — {listing.title}")
    result = score_listing(listing, profile, settings)

    tracker = get_tracker(settings)
    tracker.load_or_create()
    tracker.upsert_role(
        listing,
        result,
        scoring_status="skipped" if result["tier"] == "skip" else "scored",
        score_payload=score_payload_json(result),
    )

    master_facts = load_master_cv_facts(
        settings,
        role_family=result.get("role_family", ""),
        company=listing.company,
    )

    if should_tailor_cv(result["score"], settings):
        cv_art = build_cv_artifact(listing, result, master_facts, settings)
        if cv_art.ok:
            tracker.mark_cv_ready(listing.slug)
            tracker.mark_draft(listing.slug)

    if should_tailor_letter(result["tier"]):
        letter_art = build_letter_artifact(listing, result, master_facts, settings)
        if letter_art.ok:
            tracker.mark_letter_ready(listing.slug)
            tracker.mark_draft(listing.slug)

    tracker.rerank()
    tracker.save()
    memory.append_role_found(listing, result)
    return result


def format_score_report(listing: JobListing, result: dict) -> str:
    lines = [
        f"Score: {result['score']}/100 [{result['tier']}]",
        f"Role family: {result['role_family']}",
        f"Source: {listing.source}",
        f"Slug: {listing.slug}",
        f"Fit: {result['fit_summary']}",
        f"Key matches: {', '.join(result['key_matches'])}",
        f"Gaps: {', '.join(result['gaps'])}",
    ]
    return "\n".join(lines)

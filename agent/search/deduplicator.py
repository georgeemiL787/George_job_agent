"""Cross-source deduplicator — removes duplicate and already-seen listings."""
from __future__ import annotations

import re

from loguru import logger

from agent.search.base import JobListing

# Source priority for keeping the best duplicate
SOURCE_PRIORITY = {
    "wuzzuf": 1,
    "indeed_eg": 2,
    "bayt": 3,
    "gulftalent": 4,
    "linkedin": 0,
    "linkedin_jobs": 0,
    "manual": 0,
}


def _normalize(text: str) -> str:
    """Lowercase and strip all non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def deduplicate(
    listings: list[JobListing],
    known_slugs: set[str],
    applications_log: str = "",
) -> list[JobListing]:
    """
    Remove duplicates across sources and against already-tracked/applied roles.

    Priority: linkedin/manual > wuzzuf > indeed_eg > bayt > gulftalent
    Dedup key: normalize(title) + normalize(company)
    """
    seen_keys: dict[str, JobListing] = {}

    # Pre-populate with known slugs from tracker (rough match on slug fragments)
    known_title_company_pairs: set[str] = set()
    for slug in known_slugs:
        # slugs are "company-title-source" — extract company+title portion
        parts = slug.rsplit("-", 1)[0]  # strip source suffix
        known_title_company_pairs.add(parts.replace("-", ""))

    for listing in listings:
        key = _normalize(listing.title) + _normalize(listing.company)

        # Skip if already tracked in Excel
        if key in known_title_company_pairs:
            logger.debug(f"Dedup: skip already-tracked '{listing.title}' @ {listing.company}")
            continue

        # Skip if already in applications log
        if (
            _normalize(listing.title) in _normalize(applications_log)
            and _normalize(listing.company) in _normalize(applications_log)
        ):
            logger.debug(f"Dedup: skip already-logged '{listing.title}' @ {listing.company}")
            continue

        if key not in seen_keys:
            seen_keys[key] = listing
        else:
            # Keep higher-priority source
            existing = seen_keys[key]
            existing_prio = SOURCE_PRIORITY.get(existing.source, 99)
            new_prio = SOURCE_PRIORITY.get(listing.source, 99)
            if new_prio < existing_prio:
                logger.debug(
                    f"Dedup: prefer {listing.source} over {existing.source} "
                    f"for '{listing.title}'"
                )
                seen_keys[key] = listing

    unique = list(seen_keys.values())
    logger.info(
        f"Dedup: {len(listings)} total → {len(unique)} unique fresh listings"
    )
    return unique

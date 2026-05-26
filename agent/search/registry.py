"""Scraper registry and source resolution."""
from __future__ import annotations

from agent.config import Settings
from agent.run_control import RunOptions
from agent.search.base import BaseScraper

_SLOW_SOURCES = frozenset({"bayt", "gulftalent", "indeed_eg"})

SOURCE_ORDER = ["wuzzuf", "linkedin_jobs", "gulftalent", "bayt", "indeed_eg"]


def build_scraper_registry() -> dict[str, type[BaseScraper]]:
    from agent.search.bayt import BaytScraper
    from agent.search.gulftalent import GulfTalentScraper
    from agent.search.linkedin_jobs import LinkedInJobsScraper
    from agent.search.wuzzuf import WuzzufScraper

    registry: dict[str, type[BaseScraper]] = {
        "wuzzuf": WuzzufScraper,
        "linkedin_jobs": LinkedInJobsScraper,
        "bayt": BaytScraper,
        "gulftalent": GulfTalentScraper,
    }
    try:
        from agent.search.indeed_eg import IndeedEgScraper

        registry["indeed_eg"] = IndeedEgScraper
    except ImportError:
        pass
    return registry


def resolve_enabled_sources(settings: Settings, options: RunOptions | None) -> set[str]:
    if options and options.sources:
        sources = {s.lower() for s in options.sources}
    else:
        sources = settings.enabled_source_set()
    if "linkedin" in sources:
        sources.add("linkedin_jobs")
        sources.discard("linkedin")
    mode = (options.mode if options else "fast").lower()
    if mode == "deep":
        sources |= {"bayt", "gulftalent", "indeed_eg"}
    if settings.skip_slow_sources and mode == "fast":
        sources -= _SLOW_SOURCES
    if mode != "deep" and not settings.enable_indeed:
        sources.discard("indeed_eg")
    return sources

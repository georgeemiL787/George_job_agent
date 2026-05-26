"""CLI scraper health check — card collect only per enabled source."""
from __future__ import annotations

from agent.config import Settings
from agent.orchestrator import _run_scraper_safe
from agent.run_control import RunOptions
from agent.scoring.scorer import queries_for_mode
from agent.search.registry import SOURCE_ORDER, build_scraper_registry, resolve_enabled_sources


def run_scrape_health(settings: Settings, *, mode: str = "fast") -> dict[str, dict]:
    opts = RunOptions(mode=mode)
    enabled = resolve_enabled_sources(settings, opts)
    registry = build_scraper_registry()
    queries = queries_for_mode(mode)[:2]
    stats: dict[str, dict] = {}
    timeout = settings.scraper_timeout_seconds
    for source in SOURCE_ORDER:
        if source not in enabled:
            continue
        cls = registry.get(source)
        if not cls:
            continue
        scraper = cls()
        _, stat = _run_scraper_safe(scraper, queries, max_results=3, timeout_seconds=timeout)
        stats[scraper.SOURCE] = {
            "count": stat.count,
            "status": stat.status,
            "message": stat.message,
            "error": stat.error,
        }
    return stats


def print_scrape_health(settings: Settings, *, mode: str = "fast") -> None:
    stats = run_scrape_health(settings, mode=mode)
    print(f"\nScraper health ({mode} mode, max 3 cards per source):\n")
    print(f"{'Source':<16} {'Count':>5}  {'Status':<10} Message")
    print("-" * 60)
    for name, row in stats.items():
        print(f"{name:<16} {row['count']:>5}  {row['status']:<10} {row.get('message') or row.get('error') or ''}")

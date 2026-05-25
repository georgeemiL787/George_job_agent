"""Main run loop — orchestrates search, scoring, tailoring, and tracking."""
from __future__ import annotations

import datetime

import pytz
from loguru import logger

from agent.artifacts import build_cv_artifact, build_letter_artifact
from agent.config import Settings, get_settings
from agent.cv.master_cv import load_master_cv_facts
from agent.memory.store import MemoryStore
from agent.notify import notify_top_roles
from agent.observability.run_report import RunReport, ScraperStat, write_run_report
from agent.scoring.scorer import SEARCH_QUERIES, score_listing
from agent.search.base import JobListing
from agent.search.deduplicator import deduplicate
from agent.tracker import get_tracker


def _scraper_stat(scraper, count: int) -> ScraperStat:
    status = getattr(scraper, "health_status", "")
    message = getattr(scraper, "health_message", "")
    if not status:
        status = "ok" if count else "empty"
    return ScraperStat(count=count, status=status, message=message)


def _collect_all_listings(settings: Settings) -> tuple[list[JobListing], dict[str, ScraperStat]]:
    """Run all scrapers; return listings and per-source stats."""
    from agent.search.bayt import BaytScraper
    from agent.search.tanqeeb import TanqeebScraper
    from agent.search.wuzzuf import WuzzufScraper

    all_listings: list[JobListing] = []
    stats: dict[str, ScraperStat] = {}
    max_per_source = settings.max_roles_per_run

    scrapers = [
        WuzzufScraper(),
        BaytScraper(),
        TanqeebScraper(),
    ]

    for scraper in scrapers:
        try:
            found = scraper.search(SEARCH_QUERIES, max_results=max_per_source)
            logger.info(f"{scraper.SOURCE}: collected {len(found)} listings")
            all_listings.extend(found)
            stats[scraper.SOURCE] = _scraper_stat(scraper, len(found))
        except Exception as e:
            logger.warning(f"{scraper.SOURCE} scraper error (skipping): {e}")
            stats[scraper.SOURCE] = ScraperStat(
                count=0,
                status="error",
                message=str(e),
                error=str(e),
            )

    try:
        from agent.search.indeed_eg import IndeedEgScraper

        indeed = IndeedEgScraper()
        found = indeed.search(SEARCH_QUERIES, max_results=max_per_source)
        logger.info(f"indeed_eg: collected {len(found)} listings")
        all_listings.extend(found)
        stats["indeed_eg"] = _scraper_stat(indeed, len(found))
    except Exception as e:
        logger.warning(f"indeed_eg scraper error (skipping): {e}")
        stats["indeed_eg"] = ScraperStat(
            count=0,
            status="error",
            message=str(e),
            error=str(e),
        )

    return all_listings, stats


def _build_run_summary(
    scored: list[tuple[JobListing, dict]],
    cv_count: int,
    letter_count: int,
) -> str:
    tz = pytz.timezone("Africa/Cairo")
    now = datetime.datetime.now(tz=tz).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"Run completed at {now} Africa/Cairo",
        f"Total roles scored: {len(scored)}",
        f"CVs tailored: {cv_count}",
        f"Cover letters written: {letter_count}",
        "",
        "Top roles this run:",
    ]
    for listing, result in scored[:5]:
        lines.append(
            f"- {listing.company} -- {listing.title} "
            f"[{result['tier']}] score={result['score']} -- {result['fit_summary'][:80]}"
        )
    return "\n".join(lines)


def run(manual: bool = False, dry_run: bool = False) -> None:
    """Full agent run: search -> deduplicate -> score -> tailor -> track -> log."""
    logger.info(f"Agent run starting (manual={manual}, dry_run={dry_run})")
    settings = get_settings()
    tz = pytz.timezone(settings.timezone)
    report = RunReport(
        timestamp=datetime.datetime.now(tz=tz).isoformat(),
        manual=manual,
        dry_run=dry_run,
    )

    for path in [
        settings.memory_path,
        settings.cv_tailored_path,
        settings.cover_letters_path,
        settings.tracker_path,
        settings.logs_path,
        settings.runs_log_path,
        settings.packages_path,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    memory = MemoryStore(settings)
    tracker = get_tracker(settings)
    tracker.load_or_create()

    logger.info("Step 1: Searching all sources...")
    all_listings, report.scrapers = _collect_all_listings(settings)
    report.raw_listings = len(all_listings)
    logger.info(f"Total raw listings collected: {report.raw_listings}")

    logger.info("Step 2: Deduplicating...")
    known_slugs = tracker.get_all_slugs()
    applications_log = memory.load_applications_log()
    fresh = deduplicate(all_listings, known_slugs, applications_log)
    report.fresh_listings = len(fresh)

    if not fresh:
        logger.info("No fresh listings to process. Run complete.")
        tracker.append_log("run_complete", "no fresh listings found")
        tracker.save()
        write_run_report(report, settings)
        return

    logger.info(f"Step 3: Scoring {len(fresh)} fresh listings...")
    profile = memory.load_profile()
    scored: list[tuple[JobListing, dict]] = []
    for listing in fresh:
        result = score_listing(listing, profile, settings)
        if result["tier"] != "skip":
            scored.append((listing, result))

    scored.sort(key=lambda x: x[1]["score"], reverse=True)
    scored = scored[: settings.max_roles_per_run]
    report.scored = len(scored)
    logger.info(f"After scoring/filtering: {report.scored} roles remain")

    if dry_run:
        logger.info("Dry run mode: printing results, no files written.")
        for listing, result in scored:
            print(
                f"  [{result['tier']:8}] {result['score']:3}/100 "
                f"{listing.company:25} -- {listing.title}"
            )
        write_run_report(report, settings)
        return

    if not scored:
        logger.info("No scored roles to track or tailor. Run complete.")
        write_run_report(report, settings)
        return

    logger.info("Step 5: Updating tracker...")
    for listing, result in scored:
        tracker.upsert_role(listing, result)

    logger.info("Step 6: Tailoring CVs and cover letters...")
    cv_count = 0
    letter_count = 0

    for listing, result in scored:
        master_facts = load_master_cv_facts(
            settings,
            role_family=result.get("role_family", ""),
            company=listing.company,
        )

        if result["score"] >= settings.min_score_to_tailor:
            cv_art = build_cv_artifact(listing, result, master_facts, settings)
            if cv_art.ok:
                tracker.mark_cv_ready(listing.slug)
                tracker.mark_draft(listing.slug)
                cv_count += 1
            else:
                report.add_failure(
                    listing.slug,
                    "cv",
                    "; ".join(cv_art.errors or ["unknown"]),
                )

        if result["tier"] in ("top", "strong"):
            letter_art = build_letter_artifact(listing, result, master_facts, settings)
            if letter_art.ok:
                tracker.mark_letter_ready(listing.slug)
                if tracker.get_row_by_slug(listing.slug):
                    tracker.mark_draft(listing.slug)
                letter_count += 1
            else:
                report.add_failure(
                    listing.slug,
                    "letter",
                    "; ".join(letter_art.errors or ["unknown"]),
                )

    tracker.rerank()
    tracker.save()

    report.tailored = cv_count
    report.letters = letter_count
    summary = _build_run_summary(scored, cv_count, letter_count)
    memory.append_run_summary(summary)
    write_run_report(report, settings)
    notify_top_roles(scored, settings)

    logger.info(
        f"Agent run complete. Roles: {report.scored}, CVs: {cv_count}, Letters: {letter_count}"
    )

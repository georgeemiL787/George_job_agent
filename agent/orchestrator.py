"""Main run loop — orchestrates search, scoring, tailoring, and tracking."""
from __future__ import annotations

import datetime
import json
import time
from typing import TYPE_CHECKING

import pytz
from loguru import logger

from agent.artifacts import build_cv_artifact, build_letter_artifact
from agent.config import Settings, get_settings
from agent.cv.master_cv import load_master_cv_facts
from agent.memory.store import MemoryStore
from agent.notify import notify_top_roles
from agent.observability.run_report import (
    RunReport,
    ScraperStat,
    prune_old_run_reports,
    write_run_report,
)
from agent.run_control import RunCancelled, RunOptions, RunStatus, get_coordinator
from agent.scoring.payload import score_payload_json
from agent.scoring.prefilter import PrefilterResult, prefilter_listing, should_llm_score
from agent.scoring.scorer import queries_for_mode, score_listing
from agent.search.base import BaseScraper, JobListing
from agent.search.deduplicator import deduplicate
from agent.search.playwright_pool import PlaywrightDetailPool
from agent.search.registry import SOURCE_ORDER, build_scraper_registry, resolve_enabled_sources
from agent.tailor_gates import should_tailor_cv, should_tailor_letter
from agent.tracker import get_tracker

if TYPE_CHECKING:
    pass

TIER_ORDER = {"top": 0, "strong": 1, "medium": 2, "stretch": 3, "skip": 4}

_SLOW_SOURCES = frozenset({"bayt", "gulftalent", "indeed_eg"})


def _scraper_stat(scraper, count: int) -> ScraperStat:
    status = getattr(scraper, "health_status", "")
    message = getattr(scraper, "health_message", "")
    if not status:
        status = "ok" if count else "empty"
    return ScraperStat(count=count, status=status, message=message)


def _run_scraper_safe(
    scraper: BaseScraper,
    queries: list[str],
    max_per_source: int,
    timeout_seconds: int,
) -> tuple[list[JobListing], ScraperStat]:
    try:
        if hasattr(scraper, "set_timeout"):
            scraper.set_timeout(timeout_seconds)  # type: ignore[attr-defined]
        found = scraper.search(queries, max_results=max_per_source)
        logger.info(f"{scraper.SOURCE}: collected {len(found)} listings")
        return found, _scraper_stat(scraper, len(found))
    except Exception as e:
        logger.warning(f"{scraper.SOURCE} scraper error (skipping): {e}")
        return [], ScraperStat(count=0, status="error", message=str(e), error=str(e))


def _max_scoring_cap(settings: Settings, options: RunOptions | None) -> int:
    mode = (options.mode if options else "fast").lower()
    if mode == "deep":
        cap = settings.deep_run_max_scoring_candidates
    else:
        cap = settings.fast_run_max_scoring_candidates
    if settings.max_scoring_candidates > 0:
        cap = min(cap, settings.max_scoring_candidates)
    return cap


def _collect_all_listings(
    settings: Settings,
    options: RunOptions | None,
    coordinator,
) -> tuple[list[JobListing], dict[str, ScraperStat], dict[str, BaseScraper]]:
    """Collect job cards from enabled sources (descriptions fetched later)."""
    enabled = resolve_enabled_sources(settings, options)
    registry = build_scraper_registry()
    order = SOURCE_ORDER
    queries = queries_for_mode(options.mode if options else "fast")

    all_listings: list[JobListing] = []
    stats: dict[str, ScraperStat] = {}
    scrapers: dict[str, BaseScraper] = {}
    max_per_source = settings.max_roles_per_run
    timeout = settings.scraper_timeout_seconds
    enabled_sources = [s for s in order if s in enabled and registry.get(s)]
    coordinator.update_progress(sources_total=len(enabled_sources), sources_done=0)

    for source in enabled_sources:
        coordinator.check_cancelled()
        coordinator.update_progress(current_source=source)
        coordinator.append_event(f"Collecting from {source}…", level="info")
        cls = registry.get(source)
        if not cls:
            continue
        scraper = cls()
        found, stat = _run_scraper_safe(scraper, queries, max_per_source, timeout)
        all_listings.extend(found)
        stats[scraper.SOURCE] = stat
        scrapers[scraper.SOURCE] = scraper
        done = coordinator.get_progress().sources_done + 1
        coordinator.update_progress(
            sources_done=done,
            collected=len(all_listings),
            current_source="",
        )
        coordinator.append_event(
            f"{scraper.SOURCE}: {stat.count} listings [{stat.status}]",
            level="error" if stat.status == "error" else "info",
        )

    return all_listings, stats, scrapers


def _card_snippet_text(listing: JobListing) -> str:
    if listing.card_snippet:
        return listing.card_snippet
    return f"{listing.title} {listing.company} {listing.location}"


def _prefilter_all(
    listings: list[JobListing],
    settings: Settings,
) -> tuple[list[tuple[JobListing, PrefilterResult]], list[tuple[JobListing, PrefilterResult]]]:
    passed: list[tuple[JobListing, PrefilterResult]] = []
    rejected: list[tuple[JobListing, PrefilterResult]] = []
    for listing in listings:
        listing.card_snippet = listing.card_snippet or _card_snippet_text(listing)
        result = prefilter_listing(listing, settings)
        if should_llm_score(result, settings):
            passed.append((listing, result))
        else:
            rejected.append((listing, result))
    passed.sort(key=lambda x: x[1].relevance_score, reverse=True)
    return passed, rejected


def _fetch_details_for_shortlist(
    candidates: list[JobListing],
    scrapers: dict[str, BaseScraper],
    settings: Settings,
    coordinator,
    cap: int,
    report: RunReport,
) -> None:
    to_fetch = candidates[:cap]
    need_fetch = [
        listing
        for listing in to_fetch
        if scrapers.get(listing.source) and not listing.description
    ]
    coordinator.update_progress(
        detail_fetches_total=len(need_fetch),
        detail_fetches_done=0,
    )
    if need_fetch:
        coordinator.append_event(
            f"Fetching descriptions for {len(need_fetch)} listings…",
            level="info",
        )
    done = 0
    with PlaywrightDetailPool(timeout_seconds=settings.scraper_timeout_seconds) as pool:
        for listing in to_fetch:
            coordinator.check_cancelled()
            scraper = scrapers.get(listing.source)
            if not scraper or listing.description:
                continue
            if pool.available and listing.source in _SLOW_SOURCES:
                listing.description = pool.fetch_via_scraper(scraper, listing)
            else:
                listing.description = scraper.fetch_description(
                    listing, timeout_seconds=settings.scraper_timeout_seconds
                )
            report.detail_fetches += 1
            done += 1
            coordinator.update_progress(detail_fetches_done=done)


def _persist_prefilter_skips(
    tracker,
    fresh: list[JobListing],
    prefilter_passed_slugs: set[str],
    prefilter_by_slug: dict[str, PrefilterResult],
    *,
    run_id: int,
    persist: bool,
) -> int:
    count = 0
    if not persist:
        return count
    for listing in fresh:
        if listing.slug in prefilter_passed_slugs:
            continue
        pf = prefilter_by_slug.get(listing.slug)
        reason = pf.reason if pf else "Failed prefilter"
        payload = json.dumps(
            {"prefilter_score": pf.relevance_score if pf else 0, "reason": reason}
        )
        prefilter_score = pf.relevance_score if pf else 0
        tracker.upsert_role(
            listing,
            {
                "score": prefilter_score,
                "tier": "skip",
                "fit_summary": reason,
                "key_matches": [],
                "gaps": [],
                "role_family": "irrelevant",
            },
            run_id=run_id,
            scoring_status="skipped",
            source_payload=payload,
        )
        count += 1
    return count


def _persist_queued_overflow(
    tracker,
    queued: list[tuple[JobListing, PrefilterResult]],
    *,
    run_id: int,
    persist: bool,
    cap: int,
) -> int:
    """Persist fresh prefilter-passed roles that exceeded the LLM scoring cap."""
    if not persist or not queued:
        return 0
    count = 0
    for listing, pf in queued:
        payload = json.dumps({"prefilter_score": pf.relevance_score, "reason": pf.reason})
        tracker.upsert_role(
            listing,
            {
                "score": pf.relevance_score,
                "tier": "skip",
                "fit_summary": f"Queued: exceeded scoring cap ({cap}); {pf.reason}",
                "key_matches": [],
                "gaps": [],
                "role_family": "irrelevant",
            },
            run_id=run_id,
            scoring_status="queued",
            source_payload=payload,
        )
        count += 1
    return count


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
        ats = result.get("ats_keywords", [])
        ats_preview = ", ".join(ats[:5]) + ("…" if len(ats) > 5 else "") if ats else "—"
        lines.append(
            f"- {listing.company} -- {listing.title} "
            f"[{result['tier']}] score={result['score']} -- {result['fit_summary'][:80]}"
        )
        lines.append(f"  Apply: {listing.apply_url}")
        lines.append(f"  ATS keywords: {ats_preview}")
    return "\n".join(lines)


def _flush_report(
    report: RunReport,
    settings: Settings,
    tracker,
    coordinator,
    *,
    final: bool = False,
) -> None:
    progress = coordinator.get_progress()
    report.run_id = progress.run_id
    report.phase = progress.phase
    report.progress = {
        **progress.to_dict(),
        "llm_calls": report.llm_calls,
        "prefilter_rejected": report.prefilter_rejected,
        "detail_fetches": report.detail_fetches,
    }
    report.phase_timings = dict(progress.phase_timings)
    write_run_report(report, settings, final=final)
    if progress.run_id:
        tracker.update_run_progress(
            progress.run_id,
            phase=progress.phase,
            progress=progress.to_dict(),
            report={
                "manual": report.manual,
                "dry_run": report.dry_run,
                "status": report.status,
                "phase": report.phase,
                "progress": report.progress,
                "scrapers": {k: {"count": v.count, "status": v.status} for k, v in report.scrapers.items()},
            },
        )


def _sort_for_artifacts(scored: list[tuple[JobListing, dict]]) -> list[tuple[JobListing, dict]]:
    return sorted(
        scored,
        key=lambda x: (TIER_ORDER.get(x[1].get("tier", "skip"), 9), -x[1].get("score", 0)),
    )


def run(
    manual: bool = False,
    dry_run: bool = False,
    options: RunOptions | None = None,
) -> None:
    """Full agent run: search → deduplicate → score → tailor → track → log."""
    coordinator = get_coordinator()
    opts = options or RunOptions(dry_run=dry_run)
    opts.dry_run = dry_run

    if not coordinator.try_start_run(opts):
        logger.warning("Run skipped: another run is already active")
        return

    settings = get_settings()
    tracker = get_tracker(settings)
    tracker.load_or_create()
    tz = pytz.timezone(settings.timezone)
    report = RunReport(
        timestamp=datetime.datetime.now(tz=tz).isoformat(),
        manual=manual,
        dry_run=dry_run,
        status=RunStatus.RUNNING.value,
    )
    run_id: int | None = None
    final_status = RunStatus.COMPLETE

    try:
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
        run_id = tracker.start_run(manual, dry_run, {"mode": opts.mode, "sources": list(opts.sources or [])})
        coordinator.set_run_id(run_id)
        report.run_id = run_id

        coordinator.set_phase("collect", message="Collecting job listings from sources")
        report.phase = "collect"
        logger.info("Phase 1: Fetching job cards from enabled sources...")
        all_listings, report.scrapers, scrapers = _collect_all_listings(settings, opts, coordinator)
        report.raw_listings = len(all_listings)
        coordinator.update_progress(collected=report.raw_listings)
        _flush_report(report, settings, tracker, coordinator)

        _log_apply_links(all_listings, settings)

        coordinator.set_phase("dedup", message="Deduplicating against known roles")
        report.phase = "dedup"
        logger.info("Deduplicating against known roles...")
        known_dedup_keys = tracker.get_known_dedup_keys()
        applications_log = memory.load_applications_log()
        fresh = deduplicate(
            all_listings,
            tracker.get_all_slugs(),
            applications_log,
            known_dedup_keys=known_dedup_keys,
        )
        report.fresh_listings = len(fresh)
        coordinator.update_progress(fresh=report.fresh_listings)
        _flush_report(report, settings, tracker, coordinator)

        if not fresh:
            logger.info("No fresh listings to process. Run complete.")
            tracker.append_log("run_complete", "no fresh listings found")
            report.status = RunStatus.COMPLETE.value
            _flush_report(report, settings, tracker, coordinator, final=True)
            tracker.finish_run(run_id, RunStatus.COMPLETE.value, {"status": "complete", "fresh": 0})
            return

        fresh_set = {listing.slug for listing in fresh}
        prefiltered, prefilter_rejected = _prefilter_all(fresh, settings)
        report.prefilter_rejected = len(prefilter_rejected)
        coordinator.update_progress(prefilter_rejected=report.prefilter_rejected)
        prefilter_by_slug = {listing.slug: pf for listing, pf in prefiltered + prefilter_rejected}

        scoring_cap = _max_scoring_cap(settings, opts)
        detail_cap = min(len(prefiltered), scoring_cap * 2)
        shortlist = [listing for listing, _ in prefiltered[:detail_cap]]
        logger.info(f"[run {run_id}] Fetching descriptions for {len(shortlist)} shortlisted listings...")
        _fetch_details_for_shortlist(shortlist, scrapers, settings, coordinator, detail_cap, report)

        prefilter_passed_slugs = {listing.slug for listing, _ in prefiltered}
        persist_scores = not dry_run or settings.persist_dry_run_scores
        skipped_prefilter = _persist_prefilter_skips(
            tracker,
            fresh,
            prefilter_passed_slugs,
            prefilter_by_slug,
            run_id=run_id,
            persist=persist_scores,
        )
        report.prefilter_rejected += skipped_prefilter

        fresh_prefiltered = [(listing, pf) for listing, pf in prefiltered if listing.slug in fresh_set]
        llm_candidates = fresh_prefiltered[:scoring_cap]
        queued_overflow = fresh_prefiltered[scoring_cap:]
        if persist_scores:
            _persist_queued_overflow(
                tracker,
                queued_overflow,
                run_id=run_id,
                persist=True,
                cap=scoring_cap,
            )

        score_target = len(llm_candidates)
        coordinator.set_phase("score", message=f"Scoring up to {score_target} listings")
        coordinator.update_progress(score_target=score_target, scored=0)
        report.phase = "score"
        logger.info(f"Phase 2: Scoring up to {len(llm_candidates)} listings...")
        profile = memory.load_profile()
        scored: list[tuple[JobListing, dict]] = []

        for listing, pf in llm_candidates:
            coordinator.check_cancelled()
            payload = json.dumps({"prefilter_score": pf.relevance_score, "reason": pf.reason})
            skip_result = {
                "score": pf.relevance_score,
                "tier": "skip",
                "fit_summary": pf.reason,
                "key_matches": [],
                "gaps": [],
                "role_family": "irrelevant",
            }
            if not should_llm_score(pf, settings):
                if persist_scores:
                    tracker.upsert_role(
                        listing,
                        skip_result,
                        run_id=run_id,
                        scoring_status="skipped",
                        source_payload=payload,
                    )
                continue

            try:
                if settings.scorer_delay_seconds > 0:
                    time.sleep(settings.scorer_delay_seconds)
                result = score_listing(listing, profile, settings)
                report.llm_calls += 1
            except Exception as e:
                logger.error(f"Score error for {listing.slug}: {e}")
                result = {
                    "score": 0,
                    "tier": "skip",
                    "fit_summary": str(e),
                    "key_matches": [],
                    "gaps": [],
                    "role_family": "irrelevant",
                    "scoring_failed": True,
                    "failure_reason": str(e),
                }
                coordinator.update_progress(
                    failed=coordinator.get_progress().failed + 1,
                    llm_calls=report.llm_calls,
                )
                coordinator.append_event(f"Score failed: {listing.slug}", level="error")
                if persist_scores:
                    tracker.upsert_role(
                        listing,
                        result,
                        run_id=run_id,
                        scoring_status="failed",
                        failure_reason=str(e),
                        source_payload=payload,
                    )
                report.add_failure(listing.slug, "score", str(e))
                continue

            if result.get("scoring_failed"):
                coordinator.update_progress(
                    failed=coordinator.get_progress().failed + 1,
                    llm_calls=report.llm_calls,
                )
                coordinator.append_event(f"Score failed: {listing.slug}", level="error")
                if persist_scores:
                    tracker.upsert_role(
                        listing,
                        result,
                        run_id=run_id,
                        scoring_status="failed",
                        failure_reason=result.get("failure_reason", ""),
                        source_payload=payload,
                    )
                report.add_failure(listing.slug, "score", result.get("failure_reason", "scoring failed"))
                continue

            scoring_status = "skipped" if result["tier"] == "skip" else "scored"
            if persist_scores:
                tracker.upsert_role(
                    listing,
                    result,
                    run_id=run_id,
                    scoring_status=scoring_status,
                    source_payload=payload,
                    score_payload=score_payload_json(result),
                )

            if result["tier"] != "skip":
                scored.append((listing, result))
                logger.info(
                    f"  ✓ {listing.company} — {listing.title} "
                    f"[{result['tier']}] {result['score']}/100 | {listing.apply_url}"
                )
            else:
                logger.debug(f"  ✗ skip: {listing.title} @ {listing.company}")

            coordinator.update_progress(
                scored=len(scored),
                llm_calls=report.llm_calls,
                prefilter_rejected=report.prefilter_rejected,
            )

        scored.sort(key=lambda x: x[1]["score"], reverse=True)
        scored = scored[: settings.max_roles_per_run]
        report.scored = len(scored)
        _flush_report(report, settings, tracker, coordinator)

        if dry_run:
            logger.info("Dry run mode: printing results, no artifacts.")
            for listing, result in scored:
                ats = result.get("ats_keywords", [])
                print(
                    f"  [{result['tier']:8}] {result['score']:3}/100 "
                    f"{listing.company:25} -- {listing.title}\n"
                    f"    Apply: {listing.apply_url}\n"
                    f"    ATS keywords: {', '.join(ats[:8])}"
                )
            if coordinator.is_cancelled():
                raise RunCancelled()
            report.status = RunStatus.COMPLETE.value
            _flush_report(report, settings, tracker, coordinator, final=True)
            tracker.finish_run(run_id, RunStatus.COMPLETE.value, {"status": "complete", "scored": report.scored})
            return

        if not scored:
            logger.info("No scored roles to tailor. Run complete.")
            report.status = RunStatus.COMPLETE.value
            _flush_report(report, settings, tracker, coordinator, final=True)
            tracker.finish_run(run_id, RunStatus.COMPLETE.value, {"status": "complete", "scored": 0})
            return

        cv_count = 0
        letter_count = 0
        ordered = _sort_for_artifacts(scored)
        tailor_target = len([r for r in ordered if should_tailor_cv(r[1]["score"], settings)])
        coordinator.set_phase("tailor", message="Tailoring CVs and cover letters")
        coordinator.update_progress(tailor_target=tailor_target, tailored=0)
        report.phase = "tailor"
        logger.info("Phase 3: Tailoring CVs and cover letters (priority queue)...")

        def _process_artifact(listing: JobListing, result: dict, *, letters: bool) -> None:
            nonlocal cv_count, letter_count
            coordinator.check_cancelled()
            master_facts = load_master_cv_facts(
                settings,
                role_family=result.get("role_family", ""),
                company=listing.company,
            )
            tracker.set_artifact_status(listing.slug, "queued")

            if should_tailor_cv(result["score"], settings):
                cv_art = build_cv_artifact(listing, result, master_facts, settings)
                if cv_art.ok:
                    tracker.mark_cv_ready(listing.slug)
                    tracker.mark_draft(listing.slug)
                    tracker.set_artifact_status(listing.slug, "cv_done")
                    cv_count += 1
                    coordinator.update_progress(tailored=cv_count + letter_count)
                    coordinator.append_event(f"CV ready: {listing.company} — {listing.title}", level="info")
                    logger.info(f"  CV ready: {listing.slug}")
                else:
                    msg = "; ".join(cv_art.errors or ["unknown"])
                    tracker.set_artifact_status(listing.slug, "failed", failure_reason=msg)
                    report.add_failure(listing.slug, "cv", msg)
                    coordinator.update_progress(failed=coordinator.get_progress().failed + 1)
                    coordinator.append_event(f"CV failed: {listing.slug} — {msg}", level="error")

            if letters and should_tailor_letter(result["tier"]):
                letter_art = build_letter_artifact(listing, result, master_facts, settings)
                if letter_art.ok:
                    tracker.mark_letter_ready(listing.slug)
                    tracker.mark_draft(listing.slug)
                    tracker.set_artifact_status(listing.slug, "letter_done")
                    letter_count += 1
                    coordinator.update_progress(tailored=cv_count + letter_count)
                else:
                    msg = "; ".join(letter_art.errors or ["unknown"])
                    tracker.set_artifact_status(listing.slug, "failed", failure_reason=msg)
                    report.add_failure(listing.slug, "letter", msg)
                    coordinator.update_progress(failed=coordinator.get_progress().failed + 1)
                    coordinator.append_event(f"Letter failed: {listing.slug} — {msg}", level="error")

        wave1 = [
            (listing, result)
            for listing, result in ordered
            if result["tier"] in ("top", "strong")
        ]
        wave2 = [
            (listing, result) for listing, result in ordered if result["tier"] == "medium"
        ]

        for listing, result in wave1:
            _process_artifact(listing, result, letters=True)
        for listing, result in wave2:
            _process_artifact(listing, result, letters=False)

        tracker.rerank()
        tracker.save()

        report.tailored = cv_count
        report.letters = letter_count
        summary = _build_run_summary(scored, cv_count, letter_count)
        memory.append_run_summary(summary)
        coordinator.set_phase("complete", message="Run complete")
        report.status = RunStatus.COMPLETE.value
        _flush_report(report, settings, tracker, coordinator, final=True)
        tracker.finish_run(
            run_id,
            RunStatus.COMPLETE.value,
            {"status": "complete", "scored": report.scored, "tailored": cv_count},
        )
        coordinator.append_event(
            f"Complete — scored {report.scored}, CVs {cv_count}, letters {letter_count}",
            level="info",
        )
        notify_top_roles(scored, settings, report=report)
        prune_old_run_reports(settings)
        logger.info(
            f"[run {run_id}] Agent run complete. Roles: {report.scored}, "
            f"CVs: {cv_count}, Letters: {letter_count}, LLM calls: {report.llm_calls}"
        )

    except RunCancelled:
        final_status = RunStatus.CANCELLED
        report.status = RunStatus.CANCELLED.value
        report.error = "Run cancelled by user"
        logger.info("Agent run cancelled")
        _flush_report(report, settings, tracker, coordinator, final=True)
        if run_id:
            tracker.finish_run(run_id, RunStatus.CANCELLED.value, {"status": "cancelled"})
    except Exception as e:
        final_status = RunStatus.FAILED
        report.status = RunStatus.FAILED.value
        report.error = str(e)
        logger.exception(f"Agent run failed: {e}")
        _flush_report(report, settings, tracker, coordinator, final=True)
        if run_id:
            tracker.finish_run(run_id, RunStatus.FAILED.value, {"status": "failed", "error": str(e)})
        raise
    finally:
        coordinator.finish_run(final_status)


def _log_apply_links(listings: list[JobListing], settings: Settings) -> None:
    """Write all fetched apply links to a rolling CSV so they are never lost."""
    import csv

    out_path = settings.logs_path / "apply_links.csv"
    write_header = not out_path.exists()
    try:
        with open(out_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["fetched_at", "source", "title", "company", "location", "apply_url"])
            for listing in listings:
                writer.writerow([
                    listing.fetched_at,
                    listing.source,
                    listing.title,
                    listing.company,
                    listing.location,
                    listing.apply_url,
                ])
        logger.info(f"Apply links logged: {out_path} ({len(listings)} entries)")
    except Exception as e:
        logger.warning(f"Could not write apply links log: {e}")

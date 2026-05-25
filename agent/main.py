"""Typer CLI entry point for the job agent."""
from __future__ import annotations

import io
import os
import sys
import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.search.linkedin_import import RoleDraft

# Force UTF-8 on Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import typer
from loguru import logger

from agent.config import get_settings

app = typer.Typer(
    name="george-job-agent",
    help="AI job search agent for George Emil Sadek.",
    add_completion=False,
)


def _setup_logging() -> None:
    settings = get_settings()
    settings.logs_path.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, colorize=False)
    logger.add(
        str(settings.logs_path / "agent.log"),
        rotation="10 MB",
        retention="30 days",
        level=settings.log_level,
        encoding="utf-8",
    )


@app.command()
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="Score only, no files written."),
) -> None:
    """Run a full search-score-tailor cycle."""
    _setup_logging()
    from agent.orchestrator import run as _run
    _run(manual=True, dry_run=dry_run)


@app.command()
def status(
    drafts_only: bool = typer.Option(False, "--drafts", help="Show only Draft roles."),
) -> None:
    """Print top roles from the tracker and last scraper run health."""
    _setup_logging()
    from agent.observability.run_report import load_latest_run_report
    from agent.tracker import get_tracker

    settings = get_settings()
    tracker = get_tracker(settings)
    tracker.load_or_create()

    latest = load_latest_run_report(settings)
    if latest:
        print("\nLast run scrapers:")
        for name, stat in latest.get("scrapers", {}).items():
            err = stat.get("error")
            count = stat.get("count", 0)
            status = stat.get("status") or ("error" if err else ("ok" if count else "empty"))
            message = stat.get("message") or err
            detail = f" - {message}" if message else ""
            print(f"  {name}: {count} listings [{status}]{detail}")

    print(f"\n{'Rank':>4}  {'Score':>5}  {'Tier':8}  {'Status':12}  {'Company':20}  Role")
    print("-" * 90)
    rows = tracker.list_pipeline_rows(drafts_only=drafts_only, include_applied=False)
    for row in rows[:20]:
        print(
            f"{row.rank:>4}  {row.score:>5}  {row.tier[:8]:8}  "
            f"{row.status[:12]:12}  {row.company[:20]:20}  {row.title[:32]}"
        )


@app.command()
def tailor(slug: str = typer.Argument(..., help="Role slug to force-tailor CV for.")) -> None:
    """Force-tailor a CV for one specific role slug."""
    _setup_logging()
    from agent.artifacts import build_cv_artifact
    from agent.cv.master_cv import load_master_cv_facts
    from agent.search.base import JobListing
    from agent.tracker import get_tracker

    settings = get_settings()
    tracker = get_tracker(settings)
    tracker.load_or_create()
    role = tracker.get_row_by_slug(slug)
    if not role:
        print(f"Slug '{slug}' not found in tracker. Use 'python -m agent status' to list slugs.")
        raise typer.Exit(1)

    listing = JobListing(
        title=role.title,
        company=role.company,
        location=role.location,
        source=role.source or "manual",
        apply_url=role.apply_url,
        slug=slug,
    )
    score_result = {
        "score": role.score or 60,
        "tier": role.tier or "medium",
        "role_family": role.role_family or "adjacent",
        "key_matches": [],
        "fit_summary": role.fit_summary,
    }

    master_facts = load_master_cv_facts(
        settings,
        role_family=score_result.get("role_family", ""),
        company=listing.company,
    )
    cv_art = build_cv_artifact(listing, score_result, master_facts, settings)
    if cv_art.ok:
        tracker.mark_cv_ready(slug)
        tracker.mark_draft(slug)
        tracker.save()
        print(f"CV tailored: {cv_art.tex_path}")
        if cv_art.pdf_path:
            print(f"PDF: {cv_art.pdf_path}")
    else:
        print("CV tailoring failed:", cv_art.errors)


def _interactive_role_draft(default_source: str) -> "RoleDraft":
    from agent.search.linkedin_import import RoleDraft, detect_source_from_url

    print("\n--- Add Role (LinkedIn / any source) ---")
    print("Templates: agent/templates/linkedin_role.json or .md\n")

    title = input("Job Title: ").strip()
    company = input("Company: ").strip()
    location = input("Location: ").strip()
    apply_url = input("Apply URL: ").strip()

    print("Paste full job description (blank line to finish):")
    lines: list[str] = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)

    source = detect_source_from_url(apply_url, default_source)
    return RoleDraft(
        title=title,
        company=company,
        location=location,
        apply_url=apply_url,
        description="\n".join(lines),
        source=source,
    )


def _run_add_role(
    *,
    role_file: str | None,
    title: str | None,
    company: str | None,
    location: str | None,
    apply_url: str | None,
    description_file: str | None,
    default_source: str,
) -> None:
    from pathlib import Path

    from agent.manual_role import format_score_report, process_manual_role
    from agent.search.linkedin_import import (
        RoleDraft,
        draft_to_listing,
        load_role_file,
        read_description_file,
        detect_source_from_url,
    )

    _setup_logging()
    settings = get_settings()

    try:
        if role_file:
            draft = load_role_file(Path(role_file))
        elif title and company and apply_url:
            if not description_file:
                print("CLI mode requires --description-file with the full JD.")
                raise typer.Exit(1)
            draft = RoleDraft(
                title=title,
                company=company,
                location=location or "",
                apply_url=apply_url,
                description=read_description_file(Path(description_file)),
                source=detect_source_from_url(apply_url, default_source),
            )
        else:
            draft = _interactive_role_draft(default_source)
    except (ValueError, OSError) as e:
        print(f"Error: {e}")
        raise typer.Exit(1) from e

    listing = draft_to_listing(draft)
    if not listing.title or not listing.company or not listing.description:
        print("Error: title, company, and description are required.")
        raise typer.Exit(1)

    print("\nProcessing role...")
    result = process_manual_role(listing, settings)
    print("\n" + format_score_report(listing, result))
    print(f"\nNext: apply at {listing.apply_url}")
    print(f"Then: python -m agent mark-applied {listing.slug}")


@app.command("add-role")
def add_role(
    file: str = typer.Option(
        "",
        "--file",
        "-f",
        help="Role JSON or Markdown file (see agent/templates/).",
    ),
    title: str = typer.Option("", "--title", help="Job title (non-interactive)."),
    company: str = typer.Option("", "--company", help="Company name."),
    location: str = typer.Option("", "--location", help="Location."),
    apply_url: str = typer.Option("", "--url", help="Apply or LinkedIn job URL."),
    description_file: str = typer.Option(
        "",
        "--description-file",
        help="Path to a text file with the full job description.",
    ),
) -> None:
    """Add a role from LinkedIn or elsewhere — interactive, file, or CLI flags."""
    _run_add_role(
        role_file=file or None,
        title=title or None,
        company=company or None,
        location=location or None,
        apply_url=apply_url or None,
        description_file=description_file or None,
        default_source="manual",
    )


@app.command("add-linkedin")
def add_linkedin(
    file: str = typer.Option(
        "",
        "--file",
        "-f",
        help="Role JSON or Markdown file (see agent/templates/).",
    ),
    title: str = typer.Option("", "--title"),
    company: str = typer.Option("", "--company"),
    location: str = typer.Option("", "--location"),
    apply_url: str = typer.Option("", "--url"),
    description_file: str = typer.Option("", "--description-file"),
) -> None:
    """Same as add-role; defaults source to linkedin when URL is ambiguous."""
    _run_add_role(
        role_file=file or None,
        title=title or None,
        company=company or None,
        location=location or None,
        apply_url=apply_url or None,
        description_file=description_file or None,
        default_source="linkedin",
    )


def _artifact_paths(settings, slug: str) -> dict[str, Path]:
    return {
        "cv_tex": settings.cv_tailored_path / f"{slug}.tex",
        "cv_pdf": settings.cv_tailored_path / f"{slug}.pdf",
        "letter_tex": settings.cover_letters_path / f"{slug}_letter.tex",
        "letter_pdf": settings.cover_letters_path / f"{slug}_letter.pdf",
    }


@app.command()
def review(slug: str = typer.Argument(..., help="Role slug to review.")) -> None:
    """Show role details and artifact paths; optionally approve."""
    from agent.tracker import get_tracker

    settings = get_settings()
    tracker = get_tracker(settings)
    tracker.load_or_create()
    role = tracker.get_row_by_slug(slug)
    if not role:
        print(f"Slug '{slug}' not found.")
        raise typer.Exit(1)

    paths = _artifact_paths(settings, slug)
    print(f"\n{role.company} -- {role.title}")
    print(f"Score: {role.score}/100  Tier: {role.tier}  Status: {role.status}")
    print(f"CV Ready: {role.cv_ready}  Letter Ready: {role.letter_ready}")
    print(f"Apply: {role.apply_url}")
    print(f"Fit: {role.fit_summary}")
    print("\nArtifacts:")
    for name, p in paths.items():
        print(f"  {name}: {p} {'OK' if p.exists() else 'missing'}")

    if typer.confirm("Approve for apply (Status → Ready)?", default=False):
        tracker.mark_ready_for_apply(slug)
        tracker.save()
        print(f"Approved '{slug}'.")


@app.command()
def approve(slug: str = typer.Argument(..., help="Role slug to approve.")) -> None:
    """Mark role Ready for apply without interactive prompt."""
    from agent.tracker import get_tracker

    settings = get_settings()
    tracker = get_tracker(settings)
    tracker.load_or_create()
    if not tracker.get_row_by_slug(slug):
        print(f"Slug '{slug}' not found.")
        raise typer.Exit(1)
    tracker.mark_ready_for_apply(slug)
    tracker.save()
    print(f"Marked '{slug}' as Ready.")


@app.command()
def package(slug: str = typer.Argument(..., help="Bundle PDFs for this slug.")) -> None:
    """Copy CV/letter files into workspace/packages/<slug>/."""
    from agent.package_role import package_role

    settings = get_settings()
    try:
        out = package_role(slug, settings)
        print(f"Apply package: {out}")
    except ValueError as e:
        print(e)
        raise typer.Exit(1) from e


@app.command("sync-master")
def sync_master() -> None:
    """Generate george_master.tex stub from cv-facts.md."""
    from agent.sync_master import sync_master_tex

    settings = get_settings()
    path = sync_master_tex(settings)
    print(f"Master stub written: {path}")


@app.command("mark-applied")
def mark_applied(
    slug: str = typer.Argument(..., help="Role slug to mark as applied."),
    date: str = typer.Option("", "--date", help="ISO date (default: today)."),
) -> None:
    """Mark a role as applied in the tracker."""
    _setup_logging()
    from agent.tracker import get_tracker

    settings = get_settings()
    applied_date = date or dt.date.today().isoformat()
    tracker = get_tracker(settings)
    tracker.load_or_create()
    tracker.mark_applied(slug, applied_date)
    tracker.save()
    print(f"Marked '{slug}' as Applied on {applied_date}.")


@app.command("export-tracker")
def export_tracker_cmd(
    output: str = typer.Option("", "--output", "-o", help="Output xlsx path."),
) -> None:
    """Export the Postgres tracker to an Excel workbook."""
    from agent.tracker.import_export import export_tracker

    settings = get_settings()
    out = export_tracker(settings, Path(output) if output else None)
    print(f"Tracker exported: {out}")


@app.command("import-tracker")
def import_tracker_cmd(
    source: str = typer.Option("", "--source", "-s", help="Source xlsx path."),
) -> None:
    """Import an existing Excel tracker into Postgres."""
    from agent.tracker.import_export import import_tracker

    settings = get_settings()
    count = import_tracker(settings, Path(source) if source else None)
    print(f"Imported {count} roles into Postgres.")


@app.command()
def web() -> None:
    """Start the local web UI and API."""
    _setup_logging()
    import uvicorn

    settings = get_settings()
    port = int(os.getenv("PORT", str(settings.web_port)))
    print(f"Starting web UI: http://{settings.web_host}:{port}")
    uvicorn.run(
        "agent.web.app:app",
        host=settings.web_host,
        port=port,
        reload=False,
    )


@app.command()
def schedule() -> None:
    """Start the 4-hour background scheduler."""
    _setup_logging()
    from agent.scheduler.job import start_scheduler
    print("Starting scheduler (Africa/Cairo, every 4 hours). Press Ctrl+C to stop.")
    start_scheduler()


if __name__ == "__main__":
    app()

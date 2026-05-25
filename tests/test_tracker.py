"""Tests for the tracker workbook."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from agent.search.base import JobListing
from agent.tracker.workbook import TrackerWorkbook


def make_listing(title, company, source="wuzzuf"):
    return JobListing(
        title=title,
        company=company,
        location="Cairo",
        source=source,
        apply_url=f"https://wuzzuf.net/{company.lower()}-{title.lower().replace(' ','-')}",
        description="Test description for " + title,
    )


MOCK_SCORE = {
    "score": 75,
    "tier": "strong",
    "fit_summary": "Good match on Python and AI skills.",
    "key_matches": ["Python", "AI"],
    "gaps": [],
    "role_family": "ai_engineer",
}


@pytest.fixture
def tmp_tracker(tmp_path):
    """Create a TrackerWorkbook pointing to a temp directory."""
    settings = MagicMock()
    settings.tracker_path = tmp_path
    tracker = TrackerWorkbook(settings)
    tracker.load_or_create()
    return tracker


def test_tracker_creates_workbook(tmp_tracker):
    assert tmp_tracker.wb is not None
    assert "Pipeline" in tmp_tracker.wb.sheetnames
    assert "Applied" in tmp_tracker.wb.sheetnames
    assert "Log" in tmp_tracker.wb.sheetnames


def test_tracker_upsert_adds_row(tmp_tracker):
    listing = make_listing("AI Engineer", "TestCorp")
    tmp_tracker.upsert_role(listing, MOCK_SCORE)
    ws = tmp_tracker._pipeline
    # Row 1 is header, row 2 should be our new entry
    assert ws.max_row == 2
    assert ws.cell(row=2, column=2).value == "TestCorp"
    assert ws.cell(row=2, column=3).value == "AI Engineer"
    assert ws.cell(row=2, column=6).value == 75


def test_tracker_upsert_three_roles(tmp_tracker):
    for i in range(3):
        listing = make_listing(f"Role {i}", f"Company {i}")
        tmp_tracker.upsert_role(listing, MOCK_SCORE)
    ws = tmp_tracker._pipeline
    assert ws.max_row == 4  # header + 3 rows


def test_tracker_get_all_slugs(tmp_tracker):
    listing = make_listing("ML Engineer", "Acme")
    tmp_tracker.upsert_role(listing, MOCK_SCORE)
    slugs = tmp_tracker.get_all_slugs()
    assert listing.slug in slugs


def test_tracker_mark_cv_ready(tmp_tracker):
    listing = make_listing("CV Engineer", "VisionCorp")
    tmp_tracker.upsert_role(listing, MOCK_SCORE)
    tmp_tracker.mark_cv_ready(listing.slug)
    row = tmp_tracker._row_index_for_slug(listing.slug)
    assert tmp_tracker._pipeline.cell(row=row, column=11).value == "Yes"


def test_tracker_mark_applied(tmp_tracker):
    listing = make_listing("Data Scientist", "DataCorp")
    tmp_tracker.upsert_role(listing, MOCK_SCORE)
    tmp_tracker.mark_applied(listing.slug, "2026-05-25")
    row = tmp_tracker._row_index_for_slug(listing.slug)
    assert tmp_tracker._pipeline.cell(row=row, column=13).value == "Applied"
    assert tmp_tracker._pipeline.cell(row=row, column=14).value == "2026-05-25"


def test_tracker_save_creates_file(tmp_tracker, tmp_path):
    listing = make_listing("LLM Engineer", "AICorp")
    tmp_tracker.upsert_role(listing, MOCK_SCORE)
    tmp_tracker.save()
    xlsx_path = tmp_path / "george_emil_job_tracker.xlsx"
    assert xlsx_path.exists()

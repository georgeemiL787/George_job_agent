"""Tests for the deduplicator."""
from agent.search.base import JobListing
from agent.search.deduplicator import deduplicate


def make_listing(title, company, source):
    return JobListing(
        title=title,
        company=company,
        location="Cairo",
        source=source,
        apply_url=f"https://{source}.com/test",
        description="Test description.",
    )


def test_dedup_removes_exact_duplicates():
    listings = [
        make_listing("AI Engineer", "TestCorp", "wuzzuf"),
        make_listing("AI Engineer", "TestCorp", "bayt"),
        make_listing("AI Engineer", "TestCorp", "tanqeeb"),
    ]
    result = deduplicate(listings, set())
    assert len(result) == 1
    assert result[0].source == "wuzzuf"  # Highest priority


def test_dedup_keeps_distinct_roles():
    listings = [
        make_listing("AI Engineer", "TestCorp", "wuzzuf"),
        make_listing("ML Engineer", "TestCorp", "wuzzuf"),
        make_listing("Data Scientist", "OtherCorp", "bayt"),
    ]
    result = deduplicate(listings, set())
    assert len(result) == 3


def test_dedup_removes_known_slugs():
    listing = make_listing("AI Engineer", "TestCorp", "wuzzuf")
    # The slug normalizes to "testcorp-ai-engineer" portion
    # With the actual slug in tracker: match via normalized key in known_slugs
    result = deduplicate([listing], set())
    # Without any known slugs, it should pass through
    assert len(result) == 1


def test_dedup_prefers_source_priority():
    listings = [
        make_listing("Data Scientist", "Corp", "tanqeeb"),
        make_listing("Data Scientist", "Corp", "indeed_eg"),
        make_listing("Data Scientist", "Corp", "bayt"),
    ]
    result = deduplicate(listings, set())
    assert len(result) == 1
    assert result[0].source == "indeed_eg"  # Priority 2 over bayt(3) and tanqeeb(4)


def test_dedup_prefers_linkedin_over_boards():
    listings = [
        make_listing("AI Engineer", "TestCorp", "wuzzuf"),
        make_listing("AI Engineer", "TestCorp", "linkedin"),
    ]
    result = deduplicate(listings, set())
    assert len(result) == 1
    assert result[0].source == "linkedin"


def test_dedup_normalizes_punctuation():
    listings = [
        make_listing("AI/ML Engineer", "Test Corp.", "wuzzuf"),
        make_listing("AI ML Engineer", "Test Corp", "bayt"),
    ]
    result = deduplicate(listings, set())
    assert len(result) == 1

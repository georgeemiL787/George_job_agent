"""Tests for pre-score heuristics."""
from agent.config import Settings
from agent.scoring.prefilter import prefilter_listing, should_llm_score
from agent.search.base import JobListing


def test_prefilter_rejects_senior_role():
    listing = JobListing(
        title="Principal ML Engineer",
        company="Co",
        location="Cairo",
        source="wuzzuf",
        apply_url="https://example.com/1",
        card_snippet="Requires 8+ years experience",
    )
    result = prefilter_listing(listing, Settings())
    assert not result.pass_llm
    assert not should_llm_score(result, Settings())


def test_prefilter_boosts_intern():
    listing = JobListing(
        title="AI Intern",
        company="Co",
        location="Cairo, Egypt",
        source="wuzzuf",
        apply_url="https://example.com/2",
        card_snippet="machine learning python pytorch internship",
    )
    result = prefilter_listing(listing, Settings(prefilter_min_score=30))
    assert result.pass_llm
    assert result.relevance_score >= 30


def test_prefilter_accepts_remote_in_description():
    listing = JobListing(
        title="ML Engineer",
        company="Co",
        location="Dubai",
        source="wuzzuf",
        apply_url="https://example.com/3",
        description="Fully remote role open to candidates in Egypt. Python pytorch.",
        card_snippet="",
    )
    result = prefilter_listing(listing, Settings(prefilter_min_score=30))
    assert result.pass_llm

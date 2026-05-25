"""Tests for the scoring module."""
import json
from unittest.mock import MagicMock, patch

import pytest

from agent.scoring.scorer import score_listing
from agent.search.base import JobListing

MOCK_SCORE_RESPONSE = json.dumps({
    "score": 78,
    "tier": "strong",
    "fit_summary": "Strong match on Python and LLM tooling. Location fits well.",
    "key_matches": ["Python", "LangChain", "FastAPI", "RAG", "Docker"],
    "gaps": ["1 year experience preferred"],
    "role_family": "ai_engineer",
})

MOCK_PROFILE = "Name: George Emil Sadek. Python, PyTorch, LangChain, FastAPI, Docker."


@pytest.fixture
def sample_listing():
    return JobListing(
        title="Junior AI Engineer",
        company="TestCorp",
        location="Cairo, Egypt",
        source="wuzzuf",
        apply_url="https://wuzzuf.net/test",
        description="We need Python, LangChain, FastAPI, Docker, RAG experience.",
    )


def test_score_listing_parses_json(sample_listing):
    mock_choice = MagicMock()
    mock_choice.message.content = MOCK_SCORE_RESPONSE
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch("agent.scoring.scorer.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        MockOpenAI.return_value = mock_client

        result = score_listing(sample_listing, MOCK_PROFILE)

    assert result["score"] == 78
    assert result["tier"] == "strong"
    assert result["role_family"] == "ai_engineer"
    assert "Python" in result["key_matches"]
    assert len(result["gaps"]) <= 3


def test_score_listing_handles_json_error(sample_listing):
    mock_choice = MagicMock()
    mock_choice.message.content = "This is not JSON at all."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch("agent.scoring.scorer.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        MockOpenAI.return_value = mock_client

        result = score_listing(sample_listing, MOCK_PROFILE)

    # Should return skip defaults after both attempts fail
    assert result["tier"] == "skip"
    assert result["score"] == 0


def test_score_listing_skips_on_api_error(sample_listing):
    with patch("agent.scoring.scorer.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API down")
        MockOpenAI.return_value = mock_client

        result = score_listing(sample_listing, MOCK_PROFILE)

    assert result["tier"] == "skip"

"""Tests for scorer rate-limit retries."""
import json
from unittest.mock import MagicMock, patch

import pytest
from openai import RateLimitError

from agent.config import Settings
from agent.scoring.scorer import score_listing
from agent.search.base import JobListing

MOCK_SCORE = json.dumps({
    "score": 80,
    "tier": "strong",
    "fit_summary": "Good fit",
    "key_matches": ["Python"],
    "gaps": [],
    "role_family": "ai_engineer",
    "reasoning": "Strong overlap",
})


@pytest.fixture
def listing():
    return JobListing(
        title="ML Engineer",
        company="Co",
        location="Cairo",
        source="wuzzuf",
        apply_url="https://example.com/j",
        description="Python ML role",
    )


def test_fast_model_tried_first(listing):
    settings = Settings(
        openrouter_api_key="k",
        scoring_model_fast="fast/model",
        scoring_model="primary/model",
        fallback_model="fallback/model",
        scorer_max_retries=1,
    )
    mock_choice = MagicMock()
    mock_choice.message.content = MOCK_SCORE
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch("agent.scoring.scorer.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        MockOpenAI.return_value = mock_client

        score_listing(listing, "profile", settings)

    first_call = mock_client.chat.completions.create.call_args_list[0]
    assert first_call.kwargs["model"] == "fast/model"


def test_retry_on_rate_limit(listing):
    settings = Settings(
        openrouter_api_key="k",
        scorer_max_retries=2,
        scorer_backoff_base_seconds=0.01,
    )
    mock_choice = MagicMock()
    mock_choice.message.content = MOCK_SCORE
    ok_response = MagicMock()
    ok_response.choices = [mock_choice]

    response = MagicMock()
    response.request = MagicMock()
    response.headers = {"retry-after": "0"}
    err = RateLimitError("rate limited", response=response, body=None)

    with patch("agent.scoring.scorer.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [err, ok_response]
        MockOpenAI.return_value = mock_client
        with patch("agent.scoring.scorer.time.sleep"):
            result = score_listing(listing, "profile", settings)

    assert result["tier"] == "strong"
    assert mock_client.chat.completions.create.call_count >= 2

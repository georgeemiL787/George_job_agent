"""LLM-based job scorer via OpenRouter (OpenAI-compatible)."""
from __future__ import annotations

import json
import random
import time

from loguru import logger
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from agent.config import Settings, get_settings
from agent.search.base import JobListing
from agent.validation.models import validate_score_result

SYSTEM_PROMPT = """\
You are a job-fit evaluator for a job search agent.
Given a job description and a candidate profile, return a JSON object with EXACTLY these fields:
- reasoning: A paragraph of chain-of-thought analysis explaining the candidate's fit (MUST BE THE FIRST FIELD).
- score: integer 0-100 (realistic acceptance probability from the candidate's perspective)
- tier: one of "top" | "strong" | "medium" | "stretch" | "skip"
- fit_summary: 2-sentence plain English summary of why this role fits or doesn't
- key_matches: list of up to 5 specific matching skills/keywords from the JD
- gaps: list of up to 3 honest gaps or concerns
- role_family: one of "ai_engineer" | "ml_engineer" | "cv_engineer" | "nlp_engineer" | "rag_engineer" | "data_scientist" | "ai_intern" | "ml_intern" | "cv_intern" | "nlp_intern" | "rag_intern" | "data_intern" | "adjacent" | "irrelevant"
  (use nlp_engineer for NLP/text-processing roles, rag_engineer for RAG/LLM-retrieval roles, *_intern for any internship variant of the matching family)
- ats_keywords: list of 10-20 exact ATS keywords extracted directly from the JD text \
(tools, frameworks, libraries, methodologies, certifications — verbatim as they appear in the JD). \
These will be injected into the tailored CV. Include only real terms, not paraphrases.

Scoring rules:
- HEAVILY REWARD: student-friendly / fresh-grad wording, 0-2 years experience requirements, Cairo/Giza location, direct AI/ML/CV/NLP/LLM/RAG stack overlap, internship titles
- PENALISE: implicit or explicit 3+ year full-time requirements, senior language, non-AI-adjacent titles, roles outside Egypt without clear remote
- Use tier "skip" if: generic software role with no AI component, outside Egypt with no remote stated, clearly requires 5+ years
- Tier mapping: top=85-100, strong=70-84, medium=55-69, stretch=40-54, skip=0-39

Return ONLY valid JSON. No preamble, no markdown fences, no explanation.
"""


def _build_user_prompt(listing: JobListing, profile: str) -> str:
    return f"""CANDIDATE PROFILE:
{profile}

JOB TITLE: {listing.title}
COMPANY: {listing.company}
LOCATION: {listing.location}
SOURCE: {listing.source}
POSTED: {listing.posted_date or 'Unknown'}

JOB DESCRIPTION:
{listing.description[:4000] if listing.description else 'No description available.'}
"""


def _skip_result(message: str) -> dict:
    return {
        "score": 0,
        "tier": "skip",
        "fit_summary": message,
        "key_matches": [],
        "gaps": ["Scoring failed"],
        "role_family": "irrelevant",
        "scoring_failed": False,
    }


def _failed_result(message: str, *, retryable: bool = False) -> dict:
    return {
        "score": 0,
        "tier": "skip",
        "fit_summary": message,
        "key_matches": [],
        "gaps": [],
        "role_family": "irrelevant",
        "scoring_failed": True,
        "retryable": retryable,
        "failure_reason": message,
    }


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        code = exc.status_code
        return code in (429, 500, 502, 503, 504)
    return False


def _retry_after_seconds(exc: Exception, attempt: int, base: float) -> float:
    if isinstance(exc, APIStatusError) and exc.response is not None:
        raw = exc.response.headers.get("retry-after") or exc.response.headers.get("Retry-After")
        if raw:
            try:
                return min(float(raw), 60.0)
            except ValueError:
                pass
    delay = min(base * (2**attempt) + random.uniform(0, 1), 60.0)
    return delay


def _call_with_retry(
    client: OpenAI,
    model: str,
    messages: list[dict],
    settings: Settings,
) -> dict | None:
    max_retries = settings.scorer_max_retries
    base = settings.scorer_backoff_base_seconds
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=2000,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            validated, errors = validate_score_result(data)
            if validated is None:
                logger.warning(f"Scorer validation failed ({model}): {errors}")
                return None
            return validated
        except json.JSONDecodeError as e:
            logger.warning(f"Scorer JSON parse error ({model}): {e}")
            return None
        except Exception as e:
            last_error = e
            if not _is_retryable(e) or attempt >= max_retries - 1:
                logger.warning(f"Scorer API error ({model}): {e}")
                break
            delay = _retry_after_seconds(e, attempt, base)
            logger.warning(f"Scorer retry {attempt + 1}/{max_retries} after {delay:.1f}s ({model}): {e}")
            time.sleep(delay)

    if last_error and _is_retryable(last_error):
        raise last_error
    return None


def score_listing(
    listing: JobListing,
    profile: str,
    settings: Settings | None = None,
) -> dict:
    """Score a single job listing. Returns dict with score, tier, etc."""
    if settings is None:
        settings = get_settings()

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://github.com/george-job-agent",
            "X-Title": "George Job Agent",
        },
    )

    user_prompt = _build_user_prompt(listing, profile)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    models: list[str] = []
    seen: set[str] = set()
    for candidate in (settings.scoring_model_fast, settings.scoring_model, settings.fallback_model):
        if candidate and candidate not in seen:
            seen.add(candidate)
            models.append(candidate)

    result: dict | None = None
    last_retryable_error: Exception | None = None

    for model in models:
        try:
            result = _call_with_retry(client, model, messages, settings)
            if result is not None:
                break
            result = _call_with_retry(
                client,
                model,
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": user_prompt + "\n\nReturn ONLY valid JSON matching the schema. No extra keys.",
                    },
                ],
                settings,
            )
            if result is not None:
                break
        except Exception as e:
            last_retryable_error = e
            if _is_retryable(e):
                logger.warning(f"Scorer model {model} exhausted retries: {e}")
                continue
            logger.error(f"Scorer non-retryable error ({model}): {e}")
            return _failed_result(str(e), retryable=False)

    if result is None:
        if last_retryable_error:
            return _failed_result(str(last_retryable_error), retryable=True)
        logger.error(f"Scorer: all models failed for '{listing.title}' @ {listing.company}")
        return _failed_result("Could not score — API error.", retryable=True)

    logger.info(
        f"Scored '{listing.title}' @ {listing.company}: "
        f"{result['score']}/100 [{result['tier']}] — {result['role_family']}"
    )
    return result


FAST_SEARCH_QUERIES = [
    "AI engineer Cairo",
    "machine learning engineer Cairo",
    "NLP engineer Cairo",
    "LLM engineer Cairo",
    "RAG engineer Cairo",
    "data scientist junior Cairo",
    "AI intern Cairo",
    "ML intern Egypt",
    "computer vision intern Egypt",
    "junior AI developer Egypt",
]

SEARCH_QUERIES = [
    "AI engineer Cairo",
    "machine learning engineer Cairo",
    "computer vision engineer Cairo",
    "NLP engineer Cairo",
    "natural language processing engineer Egypt",
    "LLM engineer Cairo",
    "RAG engineer Cairo",
    "retrieval augmented generation engineer Egypt",
    "data scientist junior Cairo",
    "applied AI engineer Cairo",
    "generative AI engineer Egypt",
    "deep learning engineer Cairo",
    "AI intern Cairo",
    "ML intern Egypt",
    "machine learning intern Cairo",
    "computer vision intern Egypt",
    "NLP intern Cairo",
    "natural language processing intern Egypt",
    "LLM intern Cairo",
    "RAG intern Egypt",
    "data science intern Cairo",
    "junior AI developer Egypt",
    "AI research intern Egypt",
    "deep learning intern Cairo",
]


def queries_for_mode(mode: str) -> list[str]:
    if mode.lower() == "deep":
        return SEARCH_QUERIES
    return FAST_SEARCH_QUERIES

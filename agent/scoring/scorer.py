"""LLM-based job scorer via OpenRouter (OpenAI-compatible)."""
from __future__ import annotations

import json

from loguru import logger
from openai import OpenAI

from agent.config import Settings, get_settings
from agent.search.base import JobListing
from agent.validation.models import validate_score_result

SYSTEM_PROMPT = """\
You are a job-fit evaluator for a job search agent.
Given a job description and a candidate profile, return a JSON object with EXACTLY these fields:
- score: integer 0-100 (realistic acceptance probability from the candidate's perspective)
- tier: one of "top" | "strong" | "medium" | "stretch" | "skip"
- fit_summary: 2-sentence plain English summary of why this role fits or doesn't
- key_matches: list of up to 5 specific matching skills/keywords from the JD
- gaps: list of up to 3 honest gaps or concerns
- role_family: one of "ai_engineer" | "ml_engineer" | "cv_engineer" | "data_scientist" | "ai_intern" | "adjacent" | "irrelevant"

Scoring rules:
- HEAVILY REWARD: student-friendly / fresh-grad wording, 0-2 years experience requirements, Cairo/Giza location, direct AI/ML/CV/NLP/LLM stack overlap
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
    }


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

    def _call(model: str, extra_user: str = "") -> dict | None:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": user_prompt + extra_user,
                    },
                ],
                temperature=0.1,
                max_tokens=512,
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
            logger.warning(f"Scorer API error ({model}): {e}")
            return None

    result = _call(settings.scoring_model)
    if result is None:
        result = _call(
            settings.scoring_model,
            "\n\nReturn ONLY valid JSON matching the schema. No extra keys.",
        )

    if result is None:
        logger.info(f"Scorer: retrying with fallback model for '{listing.title}'")
        result = _call(settings.fallback_model)

    if result is None:
        logger.error(f"Scorer: both models failed for '{listing.title}' @ {listing.company}")
        return _skip_result("Could not score — API error.")

    logger.info(
        f"Scored '{listing.title}' @ {listing.company}: "
        f"{result['score']}/100 [{result['tier']}] — {result['role_family']}"
    )
    return result


SEARCH_QUERIES = [
    "AI engineer Cairo",
    "machine learning engineer Cairo",
    "computer vision engineer Cairo",
    "NLP engineer Cairo",
    "LLM engineer Cairo",
    "data scientist junior Cairo",
    "AI intern Cairo",
    "ML intern Egypt",
    "junior AI developer Egypt",
    "applied AI engineer Cairo",
]

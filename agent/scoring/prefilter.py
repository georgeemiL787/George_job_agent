"""Heuristic pre-filter before LLM scoring to reduce API calls."""
from __future__ import annotations

import re
from dataclasses import dataclass

from agent.config import Settings
from agent.search.base import JobListing

AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "ml", "deep learning",
    "nlp", "natural language", "computer vision", "cv engineer", "llm", "rag",
    "generative", "pytorch", "tensorflow", "langchain", "transformer",
    "data scientist", "data science",
]

SENIORITY_REJECT = re.compile(
    r"\b(5\+|6\+|7\+|8\+|9\+|10\+)\s*years?\b|"
    r"\b(principal|staff|director|head of|vp |vice president|lead architect)\b",
    re.I,
)

INTERN_BOOST = re.compile(
    r"\b(intern|internship|junior|fresh grad|graduate|entry[\s-]?level|trainee)\b",
    re.I,
)

EGYPT_REMOTE = re.compile(
    r"\b(egypt|cairo|giza|alexandria|alex|remote|wfh|work from home|hybrid)\b",
    re.I,
)

GENERIC_SW = re.compile(
    r"\b(frontend|front-end|backend|back-end|full[\s-]?stack|devops|qa engineer|"
    r"android|ios developer|wordpress|php developer)\b",
    re.I,
)


@dataclass
class PrefilterResult:
    pass_llm: bool
    relevance_score: int
    reason: str


def prefilter_listing(listing: JobListing, settings: Settings | None = None) -> PrefilterResult:
    text = " ".join(
        filter(
            None,
            [listing.title, listing.location, listing.card_snippet, listing.description[:500]],
        )
    ).lower()

    if SENIORITY_REJECT.search(text):
        return PrefilterResult(False, 0, "Senior/experience requirement too high")

    loc_text = f"{listing.title} {listing.location} {listing.card_snippet}".lower()
    if not EGYPT_REMOTE.search(loc_text):
        return PrefilterResult(False, 0, "Location outside Egypt without remote signal")

    title_lower = listing.title.lower()
    has_ai = any(kw in text for kw in AI_KEYWORDS)
    if GENERIC_SW.search(title_lower) and not has_ai:
        return PrefilterResult(False, 5, "Generic software role without AI keywords")

    score = 0
    for kw in AI_KEYWORDS:
        if kw in text:
            score += 12
    if INTERN_BOOST.search(text):
        score += 25
    if "cairo" in text or "giza" in text:
        score += 10
    if "remote" in text or "wfh" in text:
        score += 8

    score = min(score, 100)
    min_score = settings.prefilter_min_score if settings else 40
    if score < min_score:
        return PrefilterResult(False, score, f"Low AI relevance ({score}/{min_score})")

    return PrefilterResult(True, score, "Passed prefilter")


def should_llm_score(result: PrefilterResult, settings: Settings | None = None) -> bool:
    if settings is None:
        return result.pass_llm
    return result.pass_llm and result.relevance_score >= settings.prefilter_min_score

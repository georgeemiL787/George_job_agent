"""Heuristic pre-filter before LLM scoring to reduce API calls."""
from __future__ import annotations

import re
from dataclasses import dataclass

from agent.config import Settings
from agent.search.base import JobListing

# Regex boundary patterns to avoid substring matches (e.g. "ai" in "email")
# We use \b but handle cases where punctuation is adjacent.
def _compile_kws(kws: list[str]) -> re.Pattern:
    # Escape keywords and join with OR
    escaped = [re.escape(k) for k in kws]
    pattern = r"\b(" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.I)

# Tier 1: Core AI Titles
CORE_AI_TITLES_KWS = [
    "ai engineer", "artificial intelligence", "machine learning", "ml engineer",
    "deep learning", "nlp", "natural language", "computer vision", "cv engineer",
    "data scientist", "data science", "llm engineer", "rag engineer"
]
CORE_AI_TITLES_RE = _compile_kws(CORE_AI_TITLES_KWS)

# Tier 2: AI Skills & Tooling
AI_SKILLS_KWS = [
    "ai", "ml", "llm", "llms", "rag", "generative", "pytorch", "tensorflow",
    "langchain", "transformer", "transformers", "huggingface", "keras", "openai", "llama",
    "prompt engineering", "deep learning"
]
AI_SKILLS_RE = _compile_kws(AI_SKILLS_KWS)

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
    title = (listing.title or "").lower()
    full_text = " ".join(
        filter(
            None,
            [listing.title, listing.location, listing.card_snippet, listing.description[:500]],
        )
    ).lower()

    # 1. Hard Rejections
    if SENIORITY_REJECT.search(full_text):
        return PrefilterResult(False, 0, "Senior/experience requirement too high")

    if not EGYPT_REMOTE.search(full_text):
        return PrefilterResult(False, 0, "Location outside Egypt without remote signal")

    has_any_ai = CORE_AI_TITLES_RE.search(full_text) or AI_SKILLS_RE.search(full_text)
    if GENERIC_SW.search(full_text) and not has_any_ai:
        return PrefilterResult(False, 5, "Generic software role without AI keywords")

    # 2. Score Calculation
    score = 0
    reason_parts = []

    # Title check (Tier 1)
    if CORE_AI_TITLES_RE.search(title):
        score += 45
        reason_parts.append("Core AI Title (+45)")
    
    # Skills density (Tier 2) - extract unique matches
    skills_found = set(AI_SKILLS_RE.findall(full_text))
    if skills_found:
        skill_score = min(len(skills_found) * 15, 45)  # Max 45 points from skills
        score += skill_score
        reason_parts.append(f"AI Skills {len(skills_found)}x (+{skill_score})")

    # Modifiers
    if INTERN_BOOST.search(full_text):
        score += 20
        reason_parts.append("Junior/Intern (+20)")
    
    if "cairo" in full_text or "giza" in full_text:
        score += 10
        reason_parts.append("Cairo/Giza (+10)")
    elif "remote" in full_text or "wfh" in full_text:
        score += 10
        reason_parts.append("Remote (+10)")

    score = min(score, 100)
    min_score = settings.prefilter_min_score if settings else 40
    
    reason = ", ".join(reason_parts) if reason_parts else "No AI signals"
    
    if score < min_score:
        return PrefilterResult(False, score, f"Low AI relevance ({score}/{min_score}): {reason}")

    return PrefilterResult(True, score, f"Passed ({score}/100): {reason}")


def should_llm_score(result: PrefilterResult, settings: Settings | None = None) -> bool:
    if settings is None:
        return result.pass_llm
    return result.pass_llm and result.relevance_score >= settings.prefilter_min_score


"""Shared tracker record models."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


@dataclass
class RoleRecord:
    slug: str
    rank: int = 0
    company: str = ""
    title: str = ""
    location: str = ""
    source: str = ""
    score: int = 0
    tier: str = ""
    role_family: str = ""
    fit_summary: str = ""
    apply_url: str = ""
    cv_ready: bool = False
    letter_ready: bool = False
    status: str = "Not Applied"
    applied_date: str | None = None
    first_seen: str | None = None
    last_updated: str | None = None
    ats_keywords: str = ""  # comma-separated ATS terms from JD
    run_id: int | None = None
    scoring_status: str = ""
    artifact_status: str = "none"
    failure_reason: str = ""
    source_payload: str = ""
    score_payload: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "RoleRecord":
        return cls(
            slug=str(data.get("slug") or ""),
            rank=int(data.get("rank") or 0),
            company=str(data.get("company") or ""),
            title=str(data.get("title") or ""),
            location=str(data.get("location") or ""),
            source=str(data.get("source") or ""),
            score=int(data.get("score") or 0),
            tier=str(data.get("tier") or ""),
            role_family=str(data.get("role_family") or ""),
            fit_summary=str(data.get("fit_summary") or ""),
            apply_url=str(data.get("apply_url") or ""),
            cv_ready=bool(data.get("cv_ready")),
            letter_ready=bool(data.get("letter_ready")),
            status=str(data.get("status") or "Not Applied"),
            applied_date=_iso(data.get("applied_date")),
            first_seen=_iso(data.get("first_seen")),
            last_updated=_iso(data.get("last_updated")),
            ats_keywords=str(data.get("ats_keywords") or ""),
            run_id=int(data["run_id"]) if data.get("run_id") is not None else None,
            scoring_status=str(data.get("scoring_status") or ""),
            artifact_status=str(data.get("artifact_status") or "none"),
            failure_reason=str(data.get("failure_reason") or ""),
            source_payload=str(data.get("source_payload") or ""),
            score_payload=str(data.get("score_payload") or ""),
        )

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "rank": self.rank,
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "source": self.source,
            "score": self.score,
            "tier": self.tier,
            "role_family": self.role_family,
            "fit_summary": self.fit_summary,
            "apply_url": self.apply_url,
            "cv_ready": self.cv_ready,
            "letter_ready": self.letter_ready,
            "status": self.status,
            "applied_date": self.applied_date,
            "first_seen": self.first_seen,
            "last_updated": self.last_updated,
            "ats_keywords": self.ats_keywords,
            "run_id": self.run_id,
            "scoring_status": self.scoring_status,
            "artifact_status": self.artifact_status,
            "failure_reason": self.failure_reason,
            "source_payload": self.source_payload,
            "score_payload": self.score_payload,
        }


def effective_score(record: RoleRecord) -> int:
    """Best available score for UI: DB column, then LLM payload, then prefilter."""
    if record.score > 0:
        return record.score
    if record.score_payload:
        try:
            payload = json.loads(record.score_payload)
            if isinstance(payload, dict) and payload.get("score") is not None:
                return int(payload["score"])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    if record.source_payload:
        try:
            payload = json.loads(record.source_payload)
            if isinstance(payload, dict) and payload.get("prefilter_score") is not None:
                return int(payload["prefilter_score"])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return int(record.score or 0)


def format_added_date(record: RoleRecord) -> str:
    """Human-readable date the role was first added to the tracker."""
    raw = record.first_seen
    if not raw:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        text = str(raw)
        return text[:10] if len(text) >= 10 else text


@dataclass
class EventRecord:
    timestamp: str | None
    event: str
    detail: str
    slug: str | None = None

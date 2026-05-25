"""Shared tracker record models."""
from __future__ import annotations

import datetime as dt
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
        }


@dataclass
class EventRecord:
    timestamp: str | None
    event: str
    detail: str
    slug: str | None = None

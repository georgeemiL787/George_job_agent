"""JobListing dataclass and abstract BaseScraper."""
from __future__ import annotations

import datetime
from datetime import timezone
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JobListing:
    title: str
    company: str
    location: str
    source: str          # "wuzzuf" | "indeed_eg" | "bayt" | "tanqeeb" | "linkedin" | "manual"
    apply_url: str
    description: str = ""
    posted_date: Optional[str] = None
    raw_html: str = ""
    slug: str = ""       # auto-generated: company-title-source, lowercased, hyphened
    fetched_at: str = field(
        default_factory=lambda: datetime.datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = make_slug(self)


def make_slug(listing: JobListing) -> str:
    raw = f"{listing.company}-{listing.title}-{listing.source}"
    slug = raw.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")[:80]
    return slug


class BaseScraper(ABC):
    SOURCE: str = ""  # override in subclass

    @abstractmethod
    def search(self, queries: list[str], max_results: int = 20) -> list[JobListing]:
        ...

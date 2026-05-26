"""LinkedIn Jobs guest API scraper — no auth, no Playwright required.

LinkedIn exposes a public guest endpoint that returns job cards as HTML
fragments.  This endpoint is not documented but is stable and widely used.

Endpoint:
  GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
      ?keywords=<query>&location=<location>&start=<offset>

Returns HTML rows that can be parsed with BeautifulSoup.
"""
from __future__ import annotations

import random
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from agent.config import get_settings
from agent.search.base import BaseScraper, JobListing

_SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)
_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
_PAGE_SIZE = 10
MAX_PAGES = 3
RETRY_LIMIT = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.linkedin.com/jobs/",
}


def _sleep() -> None:
    time.sleep(1.2 + random.uniform(-0.2, 0.4))


def _get(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response | None:
    delay = 2.0
    for attempt in range(RETRY_LIMIT):
        try:
            resp = client.get(
                url,
                params=params,
                headers=HEADERS,
                follow_redirects=True,
                timeout=15,
            )
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(f"LinkedIn {resp.status_code}, retry {attempt + 1}")
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code in (403, 401):
                logger.warning(f"LinkedIn blocked ({resp.status_code}): {url}")
                return None
            resp.raise_for_status()
            return resp
        except httpx.TimeoutException:
            logger.warning(f"LinkedIn timeout, retry {attempt + 1}")
            time.sleep(delay)
            delay *= 2
        except httpx.HTTPStatusError as e:
            logger.warning(f"LinkedIn HTTP error: {e}")
            return None
    return None


def _fetch_description(client: httpx.Client, job_id: str) -> str:
    """Fetch the full JD from LinkedIn's guest job posting API."""
    if not job_id:
        return ""
    _sleep()
    url = _DETAIL_URL.format(job_id=job_id)
    resp = _get(client, url)
    if not resp:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    # Primary: description__text div
    desc = soup.find("div", {"class": lambda c: c and "description__text" in " ".join(c) if c else False})
    if desc:
        return desc.get_text(separator="\n", strip=True)
    # Fallback: show-more-less-html markup
    desc = soup.find("div", {"class": lambda c: c and "show-more-less-html__markup" in " ".join(c) if c else False})
    if desc:
        return desc.get_text(separator="\n", strip=True)
    body = soup.find("body")
    return body.get_text(separator="\n", strip=True)[:4000] if body else ""



def _linkedin_tpr(hours: int) -> str | None:
    """Map hours to LinkedIn guest API f_TPR filter (None = no time filter)."""
    if hours <= 0:
        return None
    if hours <= 24:
        return "r86400"
    if hours <= 168:
        return "r604800"
    return "r2592000"


def _extract_job_id(apply_url: str) -> str:
    """Extract the LinkedIn job ID from a job URL."""
    # e.g. https://www.linkedin.com/jobs/view/1234567890/
    parts = apply_url.rstrip("/").split("/")
    for part in reversed(parts):
        if part.isdigit():
            return part
    return ""


class LinkedInJobsScraper(BaseScraper):
    """Scrapes LinkedIn's public guest jobs API — no login required."""

    SOURCE = "linkedin_jobs"

    def __init__(self) -> None:
        self.health_status = "empty"
        self.health_message = ""

    def search(
        self,
        queries: list[str],
        max_results: int = 20,
        location: str = "Egypt",
    ) -> list[JobListing]:
        results: list[JobListing] = []
        seen_ids: set[str] = set()

        tpr = _linkedin_tpr(get_settings().linkedin_posted_within_hours)

        with httpx.Client() as client:
            for query in queries:
                if len(results) >= max_results:
                    break

                for page in range(MAX_PAGES):
                    if len(results) >= max_results:
                        break

                    params: dict[str, str | int] = {
                        "keywords": query,
                        "location": location,
                        "start": page * _PAGE_SIZE,
                    }
                    if tpr and page == 0:
                        params["f_TPR"] = tpr

                    logger.debug(f"LinkedIn search: {query!r} page {page}")
                    _sleep()
                    resp = _get(client, _SEARCH_URL, params=params)
                    if not resp or not resp.text.strip():
                        if page == 0:
                            self.health_status = "blocked"
                            self.health_message = "LinkedIn guest API returned empty/blocked"
                        break

                    soup = BeautifulSoup(resp.text, "lxml")
                    # Each job card is a <li> element
                    cards = soup.find_all("li")
                    if not cards:
                        logger.debug(f"LinkedIn: no cards page {page} for '{query}'")
                        break

                    for card in cards:
                        if len(results) >= max_results:
                            break
                        try:
                            # Job ID from data-entity-urn or from the entity link
                            entity_urn = card.get("data-entity-urn", "")
                            job_id = entity_urn.split(":")[-1] if entity_urn else ""

                            title_tag = card.find(
                                "h3",
                                {"class": lambda c: c and "base-search-card__title" in " ".join(c) if c else False},
                            ) or card.find("h3") or card.find("h2")
                            if not title_tag:
                                continue
                            title = title_tag.get_text(strip=True)

                            company_tag = card.find(
                                ["h4", "a"],
                                {"class": lambda c: c and "company" in " ".join(c).lower() if c else False},
                            ) or card.find("h4")
                            company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                            loc_tag = card.find(
                                "span",
                                {"class": lambda c: c and "location" in " ".join(c).lower() if c else False},
                            )
                            location_text = loc_tag.get_text(strip=True) if loc_tag else "Egypt"

                            # Apply URL — LinkedIn job permalink
                            link_tag = card.find("a", href=lambda h: h and "/jobs/view/" in h)
                            if not link_tag:
                                link_tag = card.find("a", href=True)
                            if not link_tag:
                                continue
                            raw_href = link_tag["href"]
                            apply_url = (
                                raw_href if raw_href.startswith("http")
                                else urljoin("https://www.linkedin.com", raw_href)
                            )
                            # Remove tracking params
                            apply_url = apply_url.split("?")[0]

                            if not job_id:
                                job_id = _extract_job_id(apply_url)
                            if job_id in seen_ids:
                                continue
                            seen_ids.add(job_id)

                            date_tag = card.find("time")
                            posted_date = (
                                date_tag.get("datetime") or date_tag.get_text(strip=True)
                                if date_tag else None
                            )

                            snippet = card.get_text(separator=" ", strip=True)[:500]

                            listing = JobListing(
                                title=title,
                                company=company,
                                location=location_text,
                                source=self.SOURCE,
                                apply_url=apply_url,
                                description="",
                                card_snippet=snippet,
                                posted_date=posted_date,
                            )
                            results.append(listing)
                            logger.info(
                                f"LinkedIn: found '{title}' @ {company} → {apply_url}"
                            )

                        except Exception as e:
                            logger.warning(f"LinkedIn card parse error: {e}")
                            continue

        if results:
            self.health_status = "ok"
        return results

    def fetch_description(self, listing: JobListing, timeout_seconds: int = 25) -> str:
        job_id = _extract_job_id(listing.apply_url)
        if not job_id:
            return ""
        with httpx.Client(timeout=timeout_seconds) as client:
            return _fetch_description(client, job_id)

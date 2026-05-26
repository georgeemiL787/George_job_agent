"""Wuzzuf Egypt scraper — httpx + BeautifulSoup4.

Card detection is structure-based (h2 > a[href^='/jobs/p/']) so it survives
CSS class renames.  Apply URL is always the canonical Wuzzuf job permalink.
"""
from __future__ import annotations

import random
import time
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup, Tag
from loguru import logger

from agent.search.base import BaseScraper, JobListing

BASE_URL = "https://wuzzuf.net/search/jobs/"
_JOB_PATH_PREFIX = "/jobs/p/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://wuzzuf.net/",
}
MAX_PAGES = 3
RETRY_LIMIT = 3


def _sleep() -> None:
    time.sleep(1.0 + random.uniform(-0.3, 0.3))


def _get_with_retry(client: httpx.Client, url: str) -> httpx.Response | None:
    delay = 2.0
    for attempt in range(RETRY_LIMIT):
        try:
            resp = client.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(f"Wuzzuf {resp.status_code} on {url}, retry {attempt + 1}")
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 403:
                logger.warning(f"Wuzzuf 403 Forbidden: {url}")
                return None
            resp.raise_for_status()
            return resp
        except httpx.TimeoutException:
            logger.warning(f"Wuzzuf timeout on {url}, retry {attempt + 1}")
            time.sleep(delay)
            delay *= 2
        except httpx.HTTPStatusError as e:
            logger.warning(f"Wuzzuf HTTP error: {e}")
            return None
    return None


def _extract_unique_job_cards(soup: BeautifulSoup) -> list[tuple[str, str, Tag]]:
    """Return list of (title, apply_url, card_tag) for all unique job cards.

    Strategy: find every <h2> whose first <a> links to /jobs/p/… — those are
    the unique job-title anchors regardless of surrounding CSS classes.
    """
    seen: set[str] = set()
    cards: list[tuple[str, str, Tag]] = []

    for h2 in soup.find_all("h2"):
        a_tag = h2.find("a", href=lambda h: h and h.startswith(_JOB_PATH_PREFIX))
        if not a_tag:
            continue
        href: str = a_tag["href"]
        apply_url = urljoin("https://wuzzuf.net", href)
        if apply_url in seen:
            continue
        seen.add(apply_url)
        title = a_tag.get_text(strip=True)
        # The card is the nearest ancestor div that also has company info
        card = h2.parent
        while card and card.name not in ("div", "article", "li"):
            card = card.parent
        if card is None:
            card = h2
        cards.append((title, apply_url, card))

    return cards


def _extract_company(card: Tag) -> str:
    """Extract company name from a card tag.

    Wuzzuf places the company anchor as the second <a> in each card
    (first is the job title, second is the company careers page).
    """
    anchors = card.find_all("a", href=True)
    for a in anchors:
        href = a.get("href", "")
        if "/jobs/careers/" in href:
            text = a.get_text(strip=True).rstrip(" -").strip()
            if text:
                return text
    return "Unknown"


def _extract_location(card: Tag) -> str:
    """Extract location from span/li text, defaulting to Egypt."""
    for tag in card.find_all(["span", "li"]):
        text = tag.get_text(strip=True)
        if any(kw in text for kw in ("Egypt", "Cairo", "Giza", "Alexandria", "Remote")):
            return text
    return "Egypt"


def _extract_posted_date(card: Tag) -> str | None:
    date_tag = card.find("time") or card.find(
        ["span", "div"],
        string=lambda s: s and ("day" in s.lower() or "month" in s.lower() or "ago" in s.lower()),
    )
    return date_tag.get_text(strip=True) if date_tag else None


def _fetch_description(client: httpx.Client, url: str) -> str:
    """Fetch the full job description from the Wuzzuf job detail page."""
    _sleep()
    resp = _get_with_retry(client, url)
    if not resp:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    desc_div = (
        soup.find("div", {"class": lambda c: c and "jb-description" in " ".join(c) if c else False})
        or soup.find("section", {"class": lambda c: c and "details" in " ".join(c) if c else False})
        or soup.find("div", {"data-scroll-target": "job-requirements"})
    )
    if desc_div:
        return desc_div.get_text(separator="\n", strip=True)
    # Broader fallback — grab main content area
    main = soup.find("main") or soup.find("article")
    return main.get_text(separator="\n", strip=True)[:4000] if main else ""


class WuzzufScraper(BaseScraper):
    SOURCE = "wuzzuf"

    def __init__(self) -> None:
        self.health_status = "empty"
        self.health_message = ""
        self._timeout = 15

    def set_timeout(self, seconds: int) -> None:
        self._timeout = seconds

    def search(self, queries: list[str], max_results: int = 20) -> list[JobListing]:
        results: list[JobListing] = []
        with httpx.Client() as client:
            for query in queries:
                if len(results) >= max_results:
                    break
                for page in range(MAX_PAGES):
                    if len(results) >= max_results:
                        break
                    params = {"q": query, "a": "hpb", "start": page * 15}
                    url = BASE_URL + "?" + urlencode(params)
                    logger.debug(f"Wuzzuf search: {url}")
                    _sleep()
                    resp = _get_with_retry(client, url)
                    if not resp:
                        break

                    soup = BeautifulSoup(resp.text, "lxml")
                    job_cards = _extract_unique_job_cards(soup)

                    if not job_cards:
                        logger.debug(f"Wuzzuf: no cards on page {page} for '{query}'")
                        break

                    logger.debug(f"Wuzzuf page {page}: {len(job_cards)} cards for '{query}'")

                    for title, apply_url, card in job_cards:
                        try:
                            company = _extract_company(card)
                            location = _extract_location(card)
                            posted_date = _extract_posted_date(card)
                            snippet = card.get_text(separator=" ", strip=True)[:500]

                            listing = JobListing(
                                title=title,
                                company=company,
                                location=location,
                                source=self.SOURCE,
                                apply_url=apply_url,
                                description="",
                                card_snippet=snippet,
                                posted_date=posted_date,
                            )
                            results.append(listing)
                            logger.info(f"Wuzzuf: found '{title}' @ {company} → {apply_url}")

                            if len(results) >= max_results:
                                break
                        except Exception as e:
                            logger.warning(f"Wuzzuf card parse error: {e}")
                            continue

        if results:
            self.health_status = "ok"
        return results

    def fetch_description(self, listing: JobListing, timeout_seconds: int = 25) -> str:
        with httpx.Client(timeout=timeout_seconds) as client:
            return _fetch_description(client, listing.apply_url)

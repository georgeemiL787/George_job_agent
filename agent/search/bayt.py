"""Bayt Egypt scraper — httpx + BeautifulSoup4."""
from __future__ import annotations

import random
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from agent.search.base import BaseScraper, JobListing

BASE_URL = "https://www.bayt.com/en/egypt/jobs/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.bayt.com/",
}
MAX_PAGES = 3
RETRY_LIMIT = 3


class ScraperBlocked(Exception):
    """Raised when Bayt blocks automated access."""


def _sleep() -> None:
    time.sleep(1.2 + random.uniform(-0.3, 0.4))


def _get_with_retry(client: httpx.Client, url: str) -> httpx.Response | None:
    delay = 2.0
    for attempt in range(RETRY_LIMIT):
        try:
            resp = client.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(f"Bayt {resp.status_code} on {url}, retry {attempt+1}")
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 403:
                raise ScraperBlocked("HTTP 403 Forbidden")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp
        except httpx.TimeoutException:
            logger.warning(f"Bayt timeout on {url}, retry {attempt+1}")
            time.sleep(delay)
            delay *= 2
        except httpx.HTTPStatusError as e:
            logger.warning(f"Bayt HTTP error: {e}")
            return None
    return None


def _query_to_slug(query: str) -> str:
    """Convert 'AI engineer Cairo' -> 'ai-engineer-cairo'"""
    return query.lower().replace(" ", "-").replace("/", "-")


def _fetch_description(client: httpx.Client, url: str) -> str:
    _sleep()
    resp = _get_with_retry(client, url)
    if not resp:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    # Bayt uses div[id*="jb-description"] or section.jb-details
    desc = (
        soup.find("div", id=lambda x: x and "jb-description" in x)
        or soup.find("div", {"class": lambda c: c and "jb-description" in c if c else False})
        or soup.find("section", {"class": lambda c: c and "jb-description" in c if c else False})
    )
    if desc:
        return desc.get_text(separator="\n", strip=True)
    # Broader fallback
    main = soup.find("main") or soup.find("article")
    return main.get_text(separator="\n", strip=True)[:3000] if main else ""


class BaytScraper(BaseScraper):
    SOURCE = "bayt"

    def search(self, queries: list[str], max_results: int = 20) -> list[JobListing]:
        self.health_status = "empty"
        self.health_message = ""
        results: list[JobListing] = []
        with httpx.Client() as client:
            for query in queries:
                if len(results) >= max_results:
                    break

                slug = _query_to_slug(query)
                for page in range(1, MAX_PAGES + 1):
                    if len(results) >= max_results:
                        break

                    # Bayt URL: /en/egypt/jobs/{slug}-jobs/?page={n}
                    if page == 1:
                        url = f"{BASE_URL}{slug}-jobs/"
                    else:
                        url = f"{BASE_URL}{slug}-jobs/?page={page}"

                    logger.debug(f"Bayt search: {url}")
                    _sleep()
                    try:
                        resp = _get_with_retry(client, url)
                    except ScraperBlocked as e:
                        self.health_status = "blocked"
                        self.health_message = str(e)
                        logger.warning(f"Bayt blocked: {e}")
                        return results
                    if not resp:
                        break

                    soup = BeautifulSoup(resp.text, "lxml")

                    # Primary selector: li[data-job-id] job cards
                    cards = soup.select("li[data-job-id]")
                    # Fallback: div.has-pointer-d job cards
                    if not cards:
                        cards = soup.select("div.has-pointer-d")
                    if not cards:
                        logger.debug(f"Bayt: no cards on page {page} for '{query}'")
                        break

                    for card in cards:
                        try:
                            title_tag = (
                                card.find("h2")
                                or card.find("a", {"class": lambda c: c and "jb-title" in c if c else False})
                            )
                            if not title_tag:
                                continue
                            title = title_tag.get_text(strip=True)

                            company_tag = card.find("b", {"itemprop": "name"}) or card.find("span", {"class": lambda c: c and "company" in c if c else False})
                            company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                            loc_tag = card.find("li", {"class": lambda c: c and "location" in c if c else False}) or card.find("span", {"itemprop": "addressLocality"})
                            location = loc_tag.get_text(strip=True) if loc_tag else "Egypt"

                            link_tag = title_tag if title_tag.name == "a" else title_tag.find("a")
                            if not link_tag or not link_tag.get("href"):
                                continue
                            apply_url = urljoin("https://www.bayt.com", link_tag["href"])

                            date_tag = card.find("li", {"class": lambda c: c and "date" in c if c else False})
                            posted_date = date_tag.get_text(strip=True) if date_tag else None

                            description = _fetch_description(client, apply_url)

                            listing = JobListing(
                                title=title,
                                company=company,
                                location=location,
                                source=self.SOURCE,
                                apply_url=apply_url,
                                description=description,
                                posted_date=posted_date,
                            )
                            results.append(listing)
                            logger.info(f"Bayt: found '{title}' @ {company}")

                            if len(results) >= max_results:
                                break
                        except Exception as e:
                            logger.warning(f"Bayt card parse error: {e}")
                            continue
        if results and self.health_status != "blocked":
            self.health_status = "ok"
        return results

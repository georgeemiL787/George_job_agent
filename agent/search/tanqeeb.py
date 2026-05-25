"""Tanqeeb Egypt scraper — httpx + BeautifulSoup4."""
from __future__ import annotations

import random
import time
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from agent.search.base import BaseScraper, JobListing

BASE_URL = "https://tanqeeb.com/jobs"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://tanqeeb.com/",
}
MAX_PAGES = 2
RETRY_LIMIT = 3


def _sleep() -> None:
    time.sleep(1.0 + random.uniform(-0.2, 0.3))


def _get_with_retry(client: httpx.Client, url: str) -> httpx.Response | None:
    delay = 2.0
    for attempt in range(RETRY_LIMIT):
        try:
            resp = client.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(f"Tanqeeb {resp.status_code} on {url}, retry {attempt+1}")
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp
        except httpx.TimeoutException:
            logger.warning(f"Tanqeeb timeout on {url}, retry {attempt+1}")
            time.sleep(delay)
            delay *= 2
        except httpx.HTTPStatusError as e:
            logger.warning(f"Tanqeeb HTTP error: {e}")
            return None
    return None


def _fetch_description(client: httpx.Client, url: str) -> str:
    _sleep()
    resp = _get_with_retry(client, url)
    if not resp:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    desc = (
        soup.find("div", {"class": lambda c: c and "job-description" in c if c else False})
        or soup.find("div", {"class": lambda c: c and "description" in c if c else False})
        or soup.find("section", {"class": lambda c: c and "details" in c if c else False})
    )
    if desc:
        return desc.get_text(separator="\n", strip=True)
    main = soup.find("main") or soup.find("article")
    return main.get_text(separator="\n", strip=True)[:3000] if main else ""


class TanqeebScraper(BaseScraper):
    SOURCE = "tanqeeb"

    def search(self, queries: list[str], max_results: int = 20) -> list[JobListing]:
        results: list[JobListing] = []
        with httpx.Client() as client:
            for query in queries:
                if len(results) >= max_results:
                    break

                for page in range(1, MAX_PAGES + 1):
                    if len(results) >= max_results:
                        break

                    params: dict = {"q": query, "country": "EG"}
                    if page > 1:
                        params["page"] = page
                    url = BASE_URL + "?" + urlencode(params)

                    logger.debug(f"Tanqeeb search: {url}")
                    _sleep()
                    resp = _get_with_retry(client, url)
                    if not resp:
                        break

                    soup = BeautifulSoup(resp.text, "lxml")

                    # Tanqeeb uses div.job-card or article.job-item
                    cards = (
                        soup.select("div.job-card")
                        or soup.select("article.job-item")
                        or soup.select("div[class*='job-card']")
                        or soup.select("li.job-listing")
                    )

                    if not cards:
                        logger.debug(f"Tanqeeb: no cards on page {page} for '{query}'")
                        break

                    for card in cards:
                        try:
                            title_tag = (
                                card.find("h2")
                                or card.find("h3")
                                or card.find("a", {"class": lambda c: c and "title" in c if c else False})
                            )
                            if not title_tag:
                                continue
                            title = title_tag.get_text(strip=True)

                            company_tag = card.find("span", {"class": lambda c: c and "company" in c if c else False}) or card.find("div", {"class": lambda c: c and "company" in c if c else False})
                            company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                            loc_tag = card.find("span", {"class": lambda c: c and "location" in c if c else False}) or card.find("div", {"class": lambda c: c and "location" in c if c else False})
                            location = loc_tag.get_text(strip=True) if loc_tag else "Egypt"

                            link_tag = title_tag if title_tag.name == "a" else title_tag.find("a")
                            if not link_tag or not link_tag.get("href"):
                                # Try finding any link in the card
                                link_tag = card.find("a", href=True)
                            if not link_tag:
                                continue
                            href = link_tag.get("href", "")
                            apply_url = href if href.startswith("http") else urljoin("https://tanqeeb.com", href)

                            date_tag = card.find("span", {"class": lambda c: c and "date" in c if c else False}) or card.find("time")
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
                            logger.info(f"Tanqeeb: found '{title}' @ {company}")

                            if len(results) >= max_results:
                                break
                        except Exception as e:
                            logger.warning(f"Tanqeeb card parse error: {e}")
                            continue
        return results

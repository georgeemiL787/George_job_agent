"""Wuzzuf Egypt scraper — httpx + BeautifulSoup4."""
from __future__ import annotations

import random
import time
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from agent.search.base import BaseScraper, JobListing

BASE_URL = "https://wuzzuf.net/search/jobs/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
                logger.warning(f"Wuzzuf {resp.status_code} on {url}, retry {attempt+1}")
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        except httpx.TimeoutException:
            logger.warning(f"Wuzzuf timeout on {url}, retry {attempt+1}")
            time.sleep(delay)
            delay *= 2
        except httpx.HTTPStatusError as e:
            logger.warning(f"Wuzzuf HTTP error: {e}")
            return None
    return None


def _fetch_description(client: httpx.Client, url: str) -> str:
    _sleep()
    resp = _get_with_retry(client, url)
    if not resp:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    desc_div = (
        soup.find("div", {"class": lambda c: c and "jb-description" in c})
        or soup.find("section", {"class": lambda c: c and "details" in c})
        or soup.find("div", {"data-scroll-target": "job-requirements"})
    )
    return desc_div.get_text(separator="\n", strip=True) if desc_div else ""


class WuzzufScraper(BaseScraper):
    SOURCE = "wuzzuf"

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
                    cards = soup.find_all("div", {"class": lambda c: c and "css-1gatmva" in c if c else False})

                    # Fallback: grab any article with job data
                    if not cards:
                        cards = soup.select("div[data-pk]") or soup.select("article.job-card")

                    if not cards:
                        logger.debug(f"Wuzzuf: no cards on page {page} for '{query}'")
                        break

                    for card in cards:
                        try:
                            title_tag = card.find("h2") or card.find("a", {"class": lambda c: c and "title" in c if c else False})
                            if not title_tag:
                                continue
                            title = title_tag.get_text(strip=True)

                            company_tag = card.find("a", {"class": lambda c: c and "company" in c if c else False})
                            company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                            loc_tag = card.find("span", {"class": lambda c: c and "location" in c if c else False})
                            location = loc_tag.get_text(strip=True) if loc_tag else "Egypt"

                            link_tag = title_tag if title_tag.name == "a" else title_tag.find("a")
                            if not link_tag or not link_tag.get("href"):
                                continue
                            apply_url = urljoin("https://wuzzuf.net", link_tag["href"])

                            date_tag = card.find("time") or card.find("span", {"class": lambda c: c and "date" in c if c else False})
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
                            logger.info(f"Wuzzuf: found '{title}' @ {company}")

                            if len(results) >= max_results:
                                break
                        except Exception as e:
                            logger.warning(f"Wuzzuf card parse error: {e}")
                            continue
        return results

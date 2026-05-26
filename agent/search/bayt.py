"""Bayt Egypt scraper — Playwright headless (bypasses Cloudflare 403).

Bayt blocks httpx/requests with a 403 Cloudflare challenge.
Using Playwright with a real Chromium binary bypasses this protection.
"""
from __future__ import annotations

import random
import time
from urllib.parse import urljoin

from loguru import logger

from agent.search.base import BaseScraper, JobListing

BASE_URL = "https://www.bayt.com/en/egypt/jobs/"
MAX_PAGES = 3
RETRY_LIMIT = 2


def _sleep() -> None:
    time.sleep(1.5 + random.uniform(-0.3, 0.5))


def _query_to_slug(query: str) -> str:
    """Convert 'AI engineer Cairo' → 'ai-engineer-cairo-jobs'"""
    slug = query.lower().replace(" ", "-").replace("/", "-")
    return f"{slug}-jobs"


class BaytScraper(BaseScraper):
    SOURCE = "bayt"

    def __init__(self) -> None:
        self.health_status = "empty"
        self.health_message = ""
        self._timeout_ms = 20000

    def set_timeout(self, seconds: int) -> None:
        self._timeout_ms = seconds * 1000

    def search(self, queries: list[str], max_results: int = 20) -> list[JobListing]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.health_status = "error"
            self.health_message = "playwright not installed"
            logger.error("playwright not installed — run: python -m playwright install chromium")
            return []

        results: list[JobListing] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            search_page = context.new_page()

            for query in queries:
                if len(results) >= max_results:
                    break

                slug = _query_to_slug(query)
                for page in range(1, MAX_PAGES + 1):
                    if len(results) >= max_results:
                        break

                    url = f"{BASE_URL}{slug}/" + (f"?page={page}" if page > 1 else "")
                    logger.debug(f"Bayt search: {url}")
                    _sleep()

                    try:
                        search_page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        # Wait for job cards to appear
                        search_page.wait_for_selector(
                            "li[data-job-id], div.has-pointer-d, [class*='job-card']",
                            timeout=12000,
                        )
                    except Exception as e:
                        logger.warning(f"Bayt page load failed: {e}")
                        self.health_status = "blocked"
                        self.health_message = str(e)
                        break

                    _sleep()

                    summaries = self._extract_card_summaries(search_page, max_results - len(results))
                    if not summaries:
                        logger.debug(f"Bayt: no cards page {page} for '{query}'")
                        break

                    for summary in summaries:
                        snippet = " ".join(
                            filter(
                                None,
                                [summary["title"], summary["company"], summary["location"]],
                            )
                        )
                        listing = JobListing(
                            title=summary["title"],
                            company=summary["company"],
                            location=summary["location"],
                            source=self.SOURCE,
                            apply_url=summary["apply_url"],
                            description="",
                            card_snippet=snippet,
                            posted_date=summary["posted_date"],
                        )
                        results.append(listing)
                        logger.info(f"Bayt: found '{listing.title}' @ {listing.company}")

                        if len(results) >= max_results:
                            break

            browser.close()

        if results:
            self.health_status = "ok"
        return results

    def fetch_description(self, listing: JobListing, timeout_seconds: int = 25) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return ""
        timeout_ms = timeout_seconds * 1000
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                return self._fetch_description(page, listing.apply_url, timeout_ms=timeout_ms)
            finally:
                browser.close()

    def _extract_card_summaries(self, page, limit: int) -> list[dict]:
        summaries: list[dict] = []
        cards = page.query_selector_all("li[data-job-id]")
        if not cards:
            cards = page.query_selector_all("div.has-pointer-d")
        if not cards:
            cards = page.query_selector_all("[class*='job-card']")

        for card in cards:
            if len(summaries) >= limit:
                break
            try:
                title_el = card.query_selector("h2, h3, a[class*='jb-title']")
                if not title_el:
                    continue
                title = title_el.inner_text().strip()

                company_el = card.query_selector(
                    "b[itemprop='name'], span[itemprop='name'], [class*='company']"
                )
                company = company_el.inner_text().strip() if company_el else "Unknown"

                loc_el = card.query_selector(
                    "li[class*='location'], span[itemprop='addressLocality'], [class*='location']"
                )
                location = loc_el.inner_text().strip() if loc_el else "Egypt"

                link_el = (
                    card.query_selector("a[href*='/job/']")
                    or card.query_selector("a[href*='bayt.com']")
                    or title_el if title_el.evaluate("el => el.tagName") == "A" else None
                )
                if not link_el:
                    link_el = card.query_selector("a[href]")
                if not link_el:
                    continue

                href = link_el.get_attribute("href") or ""
                apply_url = href if href.startswith("http") else urljoin("https://www.bayt.com", href)

                date_el = card.query_selector("li[class*='date'], span[class*='date'], time")
                posted_date = date_el.inner_text().strip() if date_el else None

                summaries.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "apply_url": apply_url,
                    "posted_date": posted_date,
                })
            except Exception as e:
                logger.warning(f"Bayt card parse error: {e}")
                continue

        return summaries

    def _fetch_description(self, page, url: str, timeout_ms: int | None = None) -> str:
        from playwright.sync_api import TimeoutError as PWTimeout
        _sleep()
        nav_timeout = timeout_ms or self._timeout_ms
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout)
            page.wait_for_selector(
                "div[id*='jb-description'], div[class*='jb-description'], section.jb-details",
                timeout=8000,
            )
            desc_el = page.query_selector(
                "div[id*='jb-description'], div[class*='jb-description'], section.jb-details"
            )
            return desc_el.inner_text().strip() if desc_el else ""
        except PWTimeout:
            logger.warning(f"Bayt description timeout: {url}")
            return ""
        except Exception as e:
            logger.warning(f"Bayt description error: {e}")
            return ""

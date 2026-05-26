"""GulfTalent Egypt scraper — Playwright headless (bypasses 403 protection).

GulfTalent (gulftalent.com) is a major MENA job board with strong Egypt
coverage.  It blocks plain httpx with a 403, so we use Playwright.

Egypt is filtered via the sidebar or by searching within the Egypt section.
"""
from __future__ import annotations

import random
import time
from urllib.parse import urljoin

from loguru import logger

from agent.search.base import BaseScraper, JobListing

_BASE = "https://www.gulftalent.com"
_EGYPT_JOBS_URL = "https://www.gulftalent.com/egypt/jobs"
MAX_PAGES = 2
RETRY_LIMIT = 2


def _sleep() -> None:
    time.sleep(1.5 + random.uniform(-0.3, 0.5))


class GulfTalentScraper(BaseScraper):
    """GulfTalent Egypt job board scraper (replaces defunct Tanqeeb)."""

    SOURCE = "gulftalent"

    def __init__(self) -> None:
        self.health_status = "empty"
        self.health_message = ""

    def search(self, queries: list[str], max_results: int = 20) -> list[JobListing]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.health_status = "error"
            self.health_message = "playwright not installed"
            logger.error("playwright not installed — run: python -m playwright install chromium")
            return []

        results: list[JobListing] = []
        seen_urls: set[str] = set()

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

                # GulfTalent search URL with keywords and Egypt filter
                search_url = f"{_EGYPT_JOBS_URL}?keywords={query.replace(' ', '+')}"
                logger.debug(f"GulfTalent search: {search_url}")
                _sleep()

                try:
                    search_page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                    search_page.wait_for_selector(
                        "[class*='job'], article, [class*='vacancy'], [class*='listing']",
                        timeout=12000,
                    )
                except Exception as e:
                    logger.warning(f"GulfTalent page load failed for '{query}': {e}")
                    self.health_status = "blocked"
                    self.health_message = str(e)
                    break

                _sleep()
                summaries = self._extract_summaries(search_page, max_results - len(results))
                if not summaries:
                    logger.debug(f"GulfTalent: no cards for '{query}'")
                    continue

                for summary in summaries:
                    if summary["apply_url"] in seen_urls:
                        continue
                    seen_urls.add(summary["apply_url"])
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
                    logger.info(f"GulfTalent: found '{listing.title}' @ {listing.company}")
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

    def _extract_summaries(self, page, limit: int) -> list[dict]:
        summaries: list[dict] = []
        # Try multiple card selectors
        cards = (
            page.query_selector_all("[class*='job-item']")
            or page.query_selector_all("article")
            or page.query_selector_all("[class*='vacancy']")
            or page.query_selector_all("[class*='listing-item']")
        )
        for card in cards:
            if len(summaries) >= limit:
                break
            try:
                title_el = card.query_selector("h2, h3, [class*='title']")
                if not title_el:
                    continue
                title = title_el.inner_text().strip()

                company_el = card.query_selector("[class*='company'], [class*='employer']")
                company = company_el.inner_text().strip() if company_el else "Unknown"

                loc_el = card.query_selector("[class*='location'], [class*='city']")
                location = loc_el.inner_text().strip() if loc_el else "Egypt"

                link_el = (
                    card.query_selector("a[href*='/jobs/']")
                    or card.query_selector("a[href*='gulftalent']")
                    or card.query_selector("a[href]")
                )
                if not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                apply_url = href if href.startswith("http") else urljoin(_BASE, href)

                date_el = card.query_selector("time, [class*='date']")
                posted_date = date_el.inner_text().strip() if date_el else None

                summaries.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "apply_url": apply_url,
                    "posted_date": posted_date,
                })
            except Exception as e:
                logger.warning(f"GulfTalent card error: {e}")
                continue
        return summaries

    def _fetch_description(self, page, url: str, timeout_ms: int = 20000) -> str:
        from playwright.sync_api import TimeoutError as PWTimeout
        _sleep()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(
                "[class*='description'], [class*='detail'], [class*='content']",
                timeout=8000,
            )
            desc_el = page.query_selector(
                "[class*='job-description'], [class*='description__text'], [class*='detail-body']"
            )
            return desc_el.inner_text().strip() if desc_el else ""
        except PWTimeout:
            logger.warning(f"GulfTalent timeout: {url}")
            return ""
        except Exception as e:
            logger.warning(f"GulfTalent description error: {e}")
            return ""

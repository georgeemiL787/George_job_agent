"""Indeed Egypt scraper — Playwright headless Chromium."""
from __future__ import annotations

import random
import time
from urllib.parse import urlencode, urljoin

from loguru import logger

from agent.search.base import BaseScraper, JobListing

BASE_URL = "https://eg.indeed.com/jobs"
MAX_PAGES = 2
RETRY_LIMIT = 2


def _sleep() -> None:
    time.sleep(1.5 + random.uniform(-0.3, 0.5))


class IndeedEgScraper(BaseScraper):
    SOURCE = "indeed_eg"

    def search(self, queries: list[str], max_results: int = 20) -> list[JobListing]:
        self.health_status = "empty"
        self.health_message = ""
        try:
            from playwright.sync_api import TimeoutError as PWTimeout
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.health_status = "error"
            self.health_message = "playwright not installed"
            logger.error("playwright not installed. Run: python -m playwright install chromium")
            return []

        results: list[JobListing] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            search_page = context.new_page()

            for query in queries:
                if len(results) >= max_results:
                    break

                for pg_num in range(MAX_PAGES):
                    if len(results) >= max_results:
                        break

                    params = {
                        "q": query,
                        "l": "Cairo, Egypt",
                        "start": pg_num * 10,
                    }
                    url = BASE_URL + "?" + urlencode(params)
                    logger.debug(f"Indeed search: {url}")

                    try:
                        search_page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        # Wait for job cards
                        search_page.wait_for_selector(
                            "#mosaic-provider-jobcards, .jobsearch-ResultsList, [data-testid='jobsearch-ResultsList']",
                            timeout=10000,
                        )
                    except PWTimeout:
                        logger.warning(f"Indeed timeout loading page {pg_num} for '{query}'")
                        break
                    except Exception as e:
                        logger.warning(f"Indeed navigation error: {e}")
                        break

                    _sleep()

                    card_summaries = self._extract_card_summaries(
                        search_page,
                        max_results - len(results),
                    )
                    if not card_summaries:
                        logger.debug(f"Indeed: no cards on page {pg_num} for '{query}'")
                        break

                    for summary in card_summaries:
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
                            card_snippet=snippet or "",
                            posted_date=summary["posted_date"],
                        )
                        results.append(listing)
                        logger.info(f"Indeed: found '{listing.title}' @ {listing.company}")

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

    def _extract_card_summaries(self, page, limit: int) -> list[dict[str, str | None]]:
        summaries: list[dict[str, str | None]] = []
        cards = page.query_selector_all(
            "div.job_seen_beacon, li.css-5lfssm, div[data-testid='jobCard']"
        )
        if not cards:
            cards = page.query_selector_all("div[class*='jobCard'], article[class*='job']")

        for card in cards:
            if len(summaries) >= limit:
                break
            try:
                title_el = card.query_selector("h2.jobTitle a, h2 a, [data-testid='jobTitle']")
                if not title_el:
                    continue
                title = title_el.inner_text().strip()

                company_el = card.query_selector(
                    "span[data-testid='company-name'], .companyName, span.css-1ioi40n"
                )
                company = company_el.inner_text().strip() if company_el else "Unknown"

                loc_el = card.query_selector(
                    "div[data-testid='text-location'], .companyLocation"
                )
                location = loc_el.inner_text().strip() if loc_el else "Egypt"

                href = title_el.get_attribute("href") or ""
                apply_url = (
                    href if href.startswith("http")
                    else urljoin("https://eg.indeed.com", href)
                )

                date_el = card.query_selector("span[data-testid='myJobsStateDate'], .date")
                posted_date = date_el.inner_text().strip() if date_el else None

                summaries.append(
                    {
                        "title": title,
                        "company": company,
                        "location": location,
                        "apply_url": apply_url,
                        "posted_date": posted_date,
                    }
                )
            except Exception as e:
                logger.warning(f"Indeed card parse error: {e}")
                continue
        return summaries

    def _fetch_description(self, page, url: str, timeout_ms: int = 20000) -> str:
        from playwright.sync_api import TimeoutError as PWTimeout
        _sleep()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(
                "#jobDescriptionText, div[data-testid='jobsearch-JobComponent-description']",
                timeout=8000,
            )
            desc_el = page.query_selector(
                "#jobDescriptionText, div[data-testid='jobsearch-JobComponent-description']"
            )
            return desc_el.inner_text().strip() if desc_el else ""
        except PWTimeout:
            logger.warning(f"Indeed description timeout: {url}")
            return ""
        except Exception as e:
            logger.warning(f"Indeed description error: {e}")
            return ""

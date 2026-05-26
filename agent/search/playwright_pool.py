"""Reusable Playwright browser for batch detail-page fetches."""
from __future__ import annotations

from loguru import logger

_SLOW_SOURCES = frozenset({"bayt", "gulftalent", "indeed_eg"})


class PlaywrightDetailPool:
    """One Chromium browser + detail page reused across listings."""

    def __init__(self, timeout_seconds: int = 25) -> None:
        self.timeout_seconds = timeout_seconds
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self) -> PlaywrightDetailPool:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("playwright not installed — detail fetches will be empty")
            return self
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._page = None
        self._browser = None
        self._playwright = None

    @property
    def available(self) -> bool:
        return self._page is not None

    def fetch_via_scraper(self, scraper, listing) -> str:
        if not self.available or listing.source not in _SLOW_SOURCES:
            return scraper.fetch_description(listing, timeout_seconds=self.timeout_seconds)
        timeout_ms = self.timeout_seconds * 1000
        return scraper._fetch_description(self._page, listing.apply_url, timeout_ms=timeout_ms)  # type: ignore[attr-defined]

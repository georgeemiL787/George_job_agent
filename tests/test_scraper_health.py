"""Scraper health reporting tests."""

from agent.config import Settings
from agent.run_control import RunOptions
from agent.search.bayt import BaytScraper
from agent.search.registry import resolve_enabled_sources


class _BlockedPage:
    def goto(self, *args, **kwargs):
        raise RuntimeError("HTTP 403 Forbidden")


class _FakeContext:
    def new_page(self):
        return _BlockedPage()


class _FakeBrowser:
    def new_context(self, *args, **kwargs):
        return _FakeContext()

    def close(self):
        pass


class _FakeChromium:
    def launch(self, *args, **kwargs):
        return _FakeBrowser()


class _FakePlaywright:
    chromium = _FakeChromium()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_bayt_403_marks_scraper_blocked(monkeypatch):
    monkeypatch.setattr("agent.search.bayt._sleep", lambda: None)
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _FakePlaywright())

    scraper = BaytScraper()
    listings = scraper.search(["AI engineer Cairo"], max_results=1)

    assert listings == []
    assert scraper.health_status == "blocked"
    assert scraper.health_message == "HTTP 403 Forbidden"


def test_resolve_sources_skips_slow_on_fast():
    settings = Settings(skip_slow_sources=True, enable_indeed=False)
    enabled = resolve_enabled_sources(settings, RunOptions(mode="fast"))
    assert "bayt" not in enabled
    assert "gulftalent" not in enabled
    assert "indeed_eg" not in enabled
    assert "wuzzuf" in enabled

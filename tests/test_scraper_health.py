"""Scraper health reporting tests."""

from agent.search.bayt import BaytScraper


def test_bayt_403_marks_scraper_blocked(httpx_mock, monkeypatch):
    monkeypatch.setattr("agent.search.bayt._sleep", lambda: None)
    httpx_mock.add_response(
        url="https://www.bayt.com/en/egypt/jobs/ai-engineer-cairo-jobs/",
        status_code=403,
    )

    scraper = BaytScraper()
    listings = scraper.search(["AI engineer Cairo"], max_results=1)

    assert listings == []
    assert scraper.health_status == "blocked"
    assert scraper.health_message == "HTTP 403 Forbidden"

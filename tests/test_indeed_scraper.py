"""Indeed scraper behavior tests."""

from unittest.mock import patch

from agent.search.indeed_eg import IndeedEgScraper


class FakeElement:
    def __init__(self, text: str = "", href: str = "") -> None:
        self.text = text
        self.href = href

    def inner_text(self) -> str:
        return self.text

    def get_attribute(self, name: str) -> str:
        return self.href if name == "href" else ""


class FakeCard:
    def query_selector(self, selector: str):
        if "jobTitle" in selector:
            return FakeElement("AI Engineer", "/rc/clk?jk=123")
        if "company-name" in selector:
            return FakeElement("Nile Bits")
        if "text-location" in selector:
            return FakeElement("Cairo")
        if "myJobsStateDate" in selector:
            return FakeElement("Posted today")
        return None


class FakePage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.gotos: list[str] = []

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.gotos.append(url)

    def wait_for_selector(self, selector: str, timeout: int) -> None:
        return None

    def query_selector_all(self, selector: str):
        return [FakeCard()] if self.name == "search" and "job_seen_beacon" in selector else []

    def query_selector(self, selector: str):
        if self.name == "detail" and "jobDescriptionText" in selector:
            return FakeElement("Python and ML role description")
        return None


class FakeContext:
    def __init__(self) -> None:
        self.search_page = FakePage("search")
        self.detail_page = FakePage("detail")
        self._pages = [self.search_page, self.detail_page]

    def new_page(self):
        return self._pages.pop(0)


class FakeBrowser:
    def __init__(self) -> None:
        self.context = FakeContext()

    def new_context(self, user_agent: str):
        return self.context

    def close(self) -> None:
        return None


class FakeChromium:
    def __init__(self) -> None:
        self.browser = FakeBrowser()

    def launch(self, headless: bool):
        return self.browser


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeChromium()


class FakePlaywrightManager:
    def __init__(self) -> None:
        self.playwright = FakePlaywright()

    def __enter__(self):
        return self.playwright

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_indeed_fetches_descriptions_on_separate_detail_page(monkeypatch):
    monkeypatch.setattr("agent.search.indeed_eg._sleep", lambda: None)
    manager = FakePlaywrightManager()

    with patch("playwright.sync_api.sync_playwright", return_value=manager):
        scraper = IndeedEgScraper()
        listings = scraper.search(["AI engineer Cairo"], max_results=1)

    context = manager.playwright.chromium.browser.context
    assert len(listings) == 1
    assert listings[0].title == "AI Engineer"
    assert listings[0].description == "Python and ML role description"
    assert context.search_page.gotos == [
        "https://eg.indeed.com/jobs?q=AI+engineer+Cairo&l=Cairo%2C+Egypt&start=0"
    ]
    assert context.detail_page.gotos == ["https://eg.indeed.com/rc/clk?jk=123"]

"""Parse Wuzzuf fixture HTML without network."""
from pathlib import Path

from bs4 import BeautifulSoup

from agent.search.base import JobListing


def _parse_cards(html: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div[data-pk]")
    results: list[JobListing] = []
    for card in cards:
        title_tag = card.find("h2")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        company_tag = card.find("a", class_=lambda c: c and "company" in c)
        company = company_tag.get_text(strip=True) if company_tag else "Unknown"
        loc_tag = card.find("span", class_=lambda c: c and "location" in c)
        location = loc_tag.get_text(strip=True) if loc_tag else "Egypt"
        link_tag = title_tag.find("a")
        apply_url = f"https://wuzzuf.net{link_tag['href']}" if link_tag and link_tag.get("href") else ""
        results.append(
            JobListing(
                title=title,
                company=company,
                location=location,
                source="wuzzuf",
                apply_url=apply_url,
                description="",
            )
        )
    return results


def test_wuzzuf_fixture_parse():
    html = Path(__file__).parent.joinpath("fixtures", "wuzzuf_sample.html").read_text(encoding="utf-8")
    listings = _parse_cards(html)
    assert len(listings) == 1
    assert listings[0].title == "Junior AI Engineer"
    assert listings[0].company == "TestCorp"

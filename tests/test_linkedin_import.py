"""Tests for LinkedIn/manual role import parsing."""
import json
from pathlib import Path

import pytest

from agent.search.linkedin_import import (
    RoleDraft,
    detect_source_from_url,
    draft_to_listing,
    load_role_file,
    parse_role_json,
    parse_role_markdown,
)


def test_detect_source_linkedin_url():
    assert detect_source_from_url("https://www.linkedin.com/jobs/view/123") == "linkedin"
    assert detect_source_from_url("https://eg.linkedin.com/jobs/view/1") == "linkedin"


def test_detect_source_other_url():
    assert detect_source_from_url("https://company.com/careers/1") == "manual"


def test_detect_source_explicit_override():
    assert detect_source_from_url("https://wuzzuf.net/jobs/x", "linkedin") == "linkedin"


def test_parse_role_json():
    payload = {
        "title": "ML Engineer",
        "company": "Corp",
        "location": "Cairo",
        "apply_url": "https://linkedin.com/jobs/view/1",
        "description": "Build models.",
    }
    draft = parse_role_json(json.dumps(payload))
    listing = draft_to_listing(draft)
    assert listing.title == "ML Engineer"
    assert listing.source == "linkedin"


def test_parse_role_markdown():
    text = """# Data Scientist
**Company:** Acme
**Location:** Giza
**URL:** https://www.linkedin.com/jobs/view/99

## Description
First line.
Second line.
"""
    draft = parse_role_markdown(text)
    assert draft.company == "Acme"
    assert "Second line" in draft.description
    listing = draft_to_listing(draft)
    assert listing.source == "linkedin"


def test_load_role_file_json(tmp_path: Path):
    path = tmp_path / "role.json"
    path.write_text(
        json.dumps(
            {
                "title": "AI Intern",
                "company": "X",
                "apply_url": "https://linkedin.com/jobs/1",
                "description": "JD",
            }
        ),
        encoding="utf-8",
    )
    draft = load_role_file(path)
    assert draft.title == "AI Intern"


def test_parse_json_missing_field():
    with pytest.raises(ValueError, match="title"):
        parse_role_json("{}")

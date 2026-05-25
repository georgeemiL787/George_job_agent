"""Parse manually captured LinkedIn (or other) roles — no scraping."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent.search.base import JobListing

def _is_linkedin_host(host: str) -> bool:
    host = host.lower().removeprefix("www.")
    return host == "linkedin.com" or host.endswith(".linkedin.com")


@dataclass
class RoleDraft:
    title: str
    company: str
    location: str
    apply_url: str
    description: str
    source: str = "linkedin"


def detect_source_from_url(url: str, explicit: str | None = None) -> str:
    """Return linkedin when URL is LinkedIn; otherwise manual unless explicit is set."""
    if explicit and explicit.strip():
        return explicit.strip().lower()
    if not url.strip():
        return "linkedin"
    try:
        if _is_linkedin_host(urlparse(url.strip()).netloc):
            return "linkedin"
    except Exception:
        pass
    return "manual"


def draft_to_listing(draft: RoleDraft) -> JobListing:
    source = detect_source_from_url(draft.apply_url, draft.source)
    return JobListing(
        title=draft.title.strip(),
        company=draft.company.strip(),
        location=draft.location.strip(),
        source=source,
        apply_url=draft.apply_url.strip(),
        description=draft.description.strip(),
    )


def _require_str(data: dict[str, Any], key: str) -> str:
    val = data.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"Missing or empty required field: {key}")
    return val.strip()


def parse_role_json(text: str) -> RoleDraft:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("JSON role file must be an object")
    return RoleDraft(
        title=_require_str(data, "title"),
        company=_require_str(data, "company"),
        location=data.get("location", "") or "",
        apply_url=_require_str(data, "apply_url"),
        description=_require_str(data, "description"),
        source=(data.get("source") or "linkedin").strip().lower(),
    )


def parse_role_markdown(text: str) -> RoleDraft:
    """
    Markdown template::

        # Job Title
        **Company:** Acme
        **Location:** Cairo
        **URL:** https://linkedin.com/jobs/view/123

        ## Description
        Full JD text...
    """
    lines = text.splitlines()
    title = ""
    company = ""
    location = ""
    apply_url = ""
    description_lines: list[str] = []
    in_description = False

    for line in lines:
        stripped = line.strip()
        if not in_description and stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
            continue
        if not in_description:
            m = re.match(r"^\*\*(Company|Location|URL):\*\*\s*(.+)$", stripped, re.I)
            if m:
                key, val = m.group(1).lower(), m.group(2).strip()
                if key == "company":
                    company = val
                elif key == "location":
                    location = val
                elif key == "url":
                    apply_url = val
                continue
            if re.match(r"^##\s*description\s*$", stripped, re.I):
                in_description = True
                continue
        if in_description:
            description_lines.append(line)

    description = "\n".join(description_lines).strip()
    if not title or not company or not apply_url or not description:
        raise ValueError(
            "Markdown role file needs # title, **Company:**, **URL:**, "
            "## Description, and body text"
        )
    return RoleDraft(
        title=title,
        company=company,
        location=location,
        apply_url=apply_url,
        description=description,
    )


def load_role_file(path: Path) -> RoleDraft:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return parse_role_json(text)
    if suffix in (".md", ".markdown"):
        return parse_role_markdown(text)
    raise ValueError(f"Unsupported role file type: {suffix} (use .json or .md)")


def read_description_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()

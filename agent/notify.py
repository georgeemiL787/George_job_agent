"""Optional post-run notifications."""
from __future__ import annotations

import subprocess
import sys

import httpx
from loguru import logger

from agent.config import Settings
from agent.search.base import JobListing

_TIER_RANK = {"top": 4, "strong": 3, "medium": 2, "stretch": 1, "skip": 0}


def _meets_tier(tier: str, min_tier: str) -> bool:
    return _TIER_RANK.get(tier, 0) >= _TIER_RANK.get(min_tier, 0)


def notify_top_roles(
    scored: list[tuple[JobListing, dict]],
    settings: Settings,
    report: object | None = None,
) -> None:
    if not settings.notify_enabled:
        return

    eligible = [
        (listing, result)
        for listing, result in scored
        if _meets_tier(result.get("tier", ""), settings.notify_min_tier)
        and result.get("score", 0) >= settings.min_score_to_tailor
    ]
    if not eligible:
        return

    lines = ["George Job Agent — top roles this run:", ""]
    if report is not None:
        lines.append(
            f"Collected: {getattr(report, 'raw_listings', 0)} | "
            f"Fresh: {getattr(report, 'fresh_listings', 0)} | "
            f"Scored: {getattr(report, 'scored', 0)} | "
            f"Failed: {len(getattr(report, 'failures', []))}"
        )
        lines.append("")
    for listing, result in eligible[:3]:
        lines.append(
            f"- {listing.company} / {listing.title} "
            f"[{result['tier']}] {result['score']}/100 — slug: {listing.slug}"
        )
    message = "\n".join(lines)

    if settings.notify_webhook_url:
        try:
            httpx.post(
                settings.notify_webhook_url,
                json={"text": message},
                timeout=10,
            )
            logger.info("Notification sent via webhook")
        except Exception as e:
            logger.warning(f"Webhook notification failed: {e}")

    if sys.platform == "win32":
        try:
            safe = message.replace('"', "'").replace("\n", " | ")
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    f'[System.Windows.Forms.MessageBox]::Show("{safe}","Job Agent")',
                ],
                check=False,
                capture_output=True,
            )
        except Exception as e:
            logger.warning(f"Windows notification failed: {e}")

"""Serialize scorer output for tracker storage."""
from __future__ import annotations

import json


def score_payload_json(result: dict) -> str:
    return json.dumps(
        {
            "score": result.get("score"),
            "tier": result.get("tier"),
            "role_family": result.get("role_family"),
            "fit_summary": result.get("fit_summary", ""),
            "key_matches": result.get("key_matches", []),
            "gaps": result.get("gaps", []),
            "reasoning": result.get("reasoning", ""),
            "retryable": result.get("retryable", False),
        }
    )

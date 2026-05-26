"""Tests for desktop role context helpers."""
from __future__ import annotations

import json

from agent.config import Settings
from agent.desktop.role_context import listing_from_role, score_result_from_role
from agent.tracker.models import RoleRecord


def test_score_result_from_role_merges_payload():
    role = RoleRecord(
        slug="co-role",
        score=75,
        tier="strong",
        role_family="ml_engineer",
        ats_keywords="Python, PyTorch",
        score_payload=json.dumps(
            {
                "key_matches": ["deep learning"],
                "gaps": ["PhD"],
                "ats_keywords": ["TensorFlow"],
            }
        ),
    )
    result = score_result_from_role(role)
    assert result["key_matches"] == ["deep learning"]
    assert "TensorFlow" in result["ats_keywords"]


def test_listing_from_role_uses_stored_description(tmp_path):
    settings = Settings(
        openrouter_api_key="k",
        workspace_dir=str(tmp_path / "workspace"),
    )
    role = RoleRecord(
        slug="co-role",
        title="ML Engineer",
        company="Acme",
        source_payload=json.dumps({"description": "Build ML pipelines with Python and PyTorch." * 5}),
    )
    listing = listing_from_role(role, settings)
    assert "ML pipelines" in listing.description

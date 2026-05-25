"""Pydantic validation for scorer JSON."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScoreResultModel(BaseModel):
    score: int = Field(ge=0, le=100)
    tier: Literal["top", "strong", "medium", "stretch", "skip"]
    fit_summary: str = ""
    key_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    role_family: Literal[
        "ai_engineer",
        "ml_engineer",
        "cv_engineer",
        "data_scientist",
        "ai_intern",
        "adjacent",
        "irrelevant",
    ] = "adjacent"

    @field_validator("key_matches", "gaps")
    @classmethod
    def trim_lists(cls, v: list[str]) -> list[str]:
        return [str(x).strip() for x in v if str(x).strip()][:5]


def validate_score_result(data: dict) -> tuple[dict | None, list[str]]:
    """Return (normalized dict, errors). None dict if invalid."""
    try:
        model = ScoreResultModel.model_validate(data)
        return model.model_dump(), []
    except Exception as e:
        return None, [str(e)]

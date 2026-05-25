"""Pydantic request models for the web API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str = ""
    apply_url: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source: str = "manual"


class MarkAppliedRequest(BaseModel):
    date: str = ""


class ScheduleConfig(BaseModel):
    enabled: bool = False
    interval_hours: int = 4


class RunRequest(BaseModel):
    dry_run: bool = False

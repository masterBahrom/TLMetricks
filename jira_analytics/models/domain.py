"""Domain models for API responses and cache structures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SyncManifest(BaseModel):
    """Metadata about the most recent sync run."""

    sync_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project: str
    jql: str
    issue_count: int = 0
    changelog_count: int = 0
    board_name: str | None = None
    board_id: int | None = None


class FieldInfo(BaseModel):
    """Discovered Jira field metadata."""

    id: str
    name: str
    custom: bool = False
    field_schema: dict[str, Any] | None = None


class StatusInfo(BaseModel):
    """Jira status with category."""

    id: str
    name: str
    category_key: str | None = None
    category_name: str | None = None


class BoardInfo(BaseModel):
    """Jira Software board summary."""

    id: int
    name: str
    type: str | None = None


class ProjectMetadata(BaseModel):
    """Discovered project metadata cached for later phases."""

    project_key: str
    jira_url: str
    story_points_field: FieldInfo | None = None
    sprint_field: FieldInfo | None = None
    fields: list[FieldInfo] = Field(default_factory=list)
    statuses: list[StatusInfo] = Field(default_factory=list)
    workflow_statuses: list[StatusInfo] = Field(default_factory=list)
    boards: list[BoardInfo] = Field(default_factory=list)
    board_configuration: dict[str, Any] | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

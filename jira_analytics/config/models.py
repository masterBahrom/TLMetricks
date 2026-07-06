"""Pydantic models for application configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class AppConfig(BaseModel):
    """Validated application configuration."""

    jira_url: str = Field(..., description="Jira Cloud base URL")
    email: str = Field(..., description="Atlassian account email")
    api_token: str = Field(..., description="Atlassian API token")
    project_key: str = Field(..., description="Jira project key")
    jql: str = Field(..., description="JQL query for issue discovery")
    cache_dir: Path = Field(default=Path("cache"), description="Local cache directory")

    @field_validator("jira_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("cache_dir", mode="before")
    @classmethod
    def coerce_cache_dir(cls, value: str | Path) -> Path:
        return Path(value)


class CacheConfig(BaseModel):
    """Minimal configuration for offline cache processing (Phase 2+)."""

    cache_dir: Path = Field(default=Path("cache"), description="Local cache directory")
    project_key: str | None = None

    @field_validator("cache_dir", mode="before")
    @classmethod
    def coerce_cache_dir(cls, value: str | Path) -> Path:
        return Path(value)

"""Timeline domain models — single source of truth for issue lifecycle."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from jira_analytics.utils.datetime_utils import utc_now


class StatusRegistryEntry(BaseModel):
    """A status known to the project, with its workflow category."""

    status_id: str
    status_name: str
    status_category: str  # new | indeterminate | done | undefined


class StatusPeriod(BaseModel):
    """A contiguous period spent in a single workflow status."""

    status_id: str
    status_name: str
    status_category: str
    entered_at: datetime
    left_at: datetime | None = None
    duration_seconds: float = 0.0
    duration_hours: float = 0.0
    is_current: bool = False
    is_done: bool = False


class FlaggedPeriod(BaseModel):
    """A contiguous period where Jira Flagged/Impediment was set."""

    started_at: datetime
    ended_at: datetime
    duration_seconds: float = 0.0
    is_open: bool = False
    source: str = "flagged"


class IssueTimeline(BaseModel):
    """Complete reconstructed lifecycle for one issue."""

    issue_key: str
    issue_id: str
    created_at: datetime
    resolution_at: datetime | None = None
    periods: list[StatusPeriod] = Field(default_factory=list)
    flagged_periods: list[FlaggedPeriod] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def current_period(self) -> StatusPeriod | None:
        current = [period for period in self.periods if period.is_current]
        return current[0] if current else None


class StatusRegistry(BaseModel):
    """Lookup table of all statuses for the project."""

    generated_at: datetime = Field(default_factory=utc_now)
    statuses: dict[str, StatusRegistryEntry] = Field(default_factory=dict)

    def lookup_by_id(self, status_id: str | None) -> StatusRegistryEntry | None:
        if not status_id:
            return None
        return self.statuses.get(str(status_id))

    def lookup_by_name(self, status_name: str | None) -> StatusRegistryEntry | None:
        if not status_name:
            return None
        normalized = status_name.strip().lower()
        for entry in self.statuses.values():
            if entry.status_name.strip().lower() == normalized:
                return entry
        return None

    def resolve(self, status_id: str | None, status_name: str | None) -> StatusRegistryEntry:
        """Resolve a status by id or name, returning a fallback entry if unknown."""
        entry = self.lookup_by_id(status_id) or self.lookup_by_name(status_name)
        if entry:
            return entry
        return StatusRegistryEntry(
            status_id=str(status_id or status_name or "unknown"),
            status_name=status_name or str(status_id or "Unknown"),
            status_category="undefined",
        )


class TimelinesDocument(BaseModel):
    """Container for all issue timelines produced by Phase 2."""

    generated_at: datetime = Field(default_factory=utc_now)
    issue_count: int = 0
    timelines: dict[str, IssueTimeline] = Field(default_factory=dict)
    validation_warnings: list[str] = Field(default_factory=list)

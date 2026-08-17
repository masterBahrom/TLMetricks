"""Metrics domain models — output of Phase 3 Metrics Engine."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from jira_analytics.utils.datetime_utils import utc_now
from jira_analytics.utils.stats import seconds_to_days, seconds_to_hours


METRICS_SCHEMA_VERSION = "2.2"


class StatusPeriodMetrics(BaseModel):
    """Single status visit on an issue timeline (for metric inspection)."""

    status: str
    entered_at: datetime
    left_at: datetime | None = None
    duration_seconds: float
    hours: float
    category: str


class TimeInStatus(BaseModel):
    """Aggregated time an issue spent in a single workflow status."""

    status: str
    duration_seconds: float
    hours: float
    days: float


class IssueMetrics(BaseModel):
    """
    Canonical representation of one Jira issue for analytics and reporting.

    Combines Jira metadata (from issues.json) with computed engineering metrics
    (from timelines). Consumers must read only metrics.json — never issues.json.
    """

    # --- Identity ---
    issue_key: str
    issue_id: str
    project_key: str | None = None

    # --- Jira metadata (enriched from issues.json) ---
    summary: str | None = None
    description: str | None = None
    assignee: str | None = None
    reporter: str | None = None
    issue_type: str | None = None
    priority: str | None = None
    story_points: float | None = None
    sprint: str | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    resolution: str | None = None
    is_bug: bool = False

    # --- Lifecycle ---
    created_date: datetime
    resolution_date: datetime | None = None
    done_date: datetime | None = None
    current_status: str | None = None
    is_done: bool = False
    is_reopened: bool = False
    reopen_count: int = 0
    status_count: int = 0

    # --- Engineering metrics ---
    lead_time_seconds: float | None = None
    lead_time_hours: float | None = None
    lead_time_days: float | None = None

    cycle_time_seconds: float | None = None
    cycle_time_hours: float | None = None
    cycle_time_days: float | None = None
    net_cycle_time_seconds: float | None = None
    net_cycle_time_hours: float | None = None

    resolution_time_seconds: float | None = None
    resolution_time_hours: float | None = None
    resolution_time_days: float | None = None

    total_active_time_seconds: float = 0.0
    total_active_time_hours: float = 0.0
    buffer_time_seconds: float = 0.0
    buffer_time_hours: float = 0.0
    terminal_time_seconds: float = 0.0
    terminal_time_hours: float = 0.0
    waiting_time_seconds: float = 0.0
    waiting_time_hours: float = 0.0
    blocked_time_seconds: float = 0.0
    blocked_time_hours: float = 0.0
    terminal_blocked_time_seconds: float = 0.0
    terminal_blocked_time_hours: float = 0.0
    time_to_first_progress_seconds: float | None = None
    time_to_first_progress_hours: float | None = None

    flow_efficiency_percent: float | None = None
    net_flow_efficiency_percent: float | None = None

    time_in_status: list[TimeInStatus] = Field(default_factory=list)
    status_periods: list[StatusPeriodMetrics] = Field(default_factory=list)


class StatusAverage(BaseModel):
    """Average time spent in a status across issues."""

    status: str
    average_seconds: float
    average_hours: float
    average_days: float
    issue_count: int


class ProjectMetrics(BaseModel):
    """Aggregated engineering metrics for the entire project."""

    project_key: str
    total_issues: int = 0
    done_count: int = 0
    open_count: int = 0
    reopened_count: int = 0
    throughput: int = 0

    average_lead_time_seconds: float | None = None
    median_lead_time_seconds: float | None = None
    p90_lead_time_seconds: float | None = None

    average_cycle_time_seconds: float | None = None
    median_cycle_time_seconds: float | None = None
    p90_cycle_time_seconds: float | None = None
    average_net_cycle_time_seconds: float | None = None
    median_net_cycle_time_seconds: float | None = None

    average_time_to_first_progress_seconds: float | None = None
    average_active_time_seconds: float | None = None
    average_buffer_time_seconds: float | None = None
    median_buffer_time_seconds: float | None = None
    p75_buffer_time_seconds: float | None = None
    p90_buffer_time_seconds: float | None = None
    p95_buffer_time_seconds: float | None = None
    total_buffer_time_seconds: float | None = None
    average_blocked_time_seconds: float | None = None
    median_blocked_time_seconds: float | None = None
    p75_blocked_time_seconds: float | None = None
    p90_blocked_time_seconds: float | None = None
    p95_blocked_time_seconds: float | None = None
    blocked_issue_count: int = 0
    blocked_issue_percent: float | None = None
    average_net_flow_efficiency_percent: float | None = None
    average_waiting_time_seconds: float | None = None
    average_reopens: float = 0.0

    completed_bugs: int = 0
    completed_hotfix: int = 0
    total_bugs: int = 0
    bug_rate_percent: float | None = None

    average_time_by_status: list[StatusAverage] = Field(default_factory=list)


class BugRateBySprint(BaseModel):
    sprint: str
    completed_bugs: int
    completed_issues: int
    bug_rate_percent: float


class BugRateByIssueType(BaseModel):
    issue_type: str
    completed_count: int
    bug_count: int


class BugAnalytics(BaseModel):
    completed_bugs: int = 0
    completed_hotfix: int = 0
    total_bugs: int = 0
    completed_issues: int = 0
    bug_rate_percent: float | None = None
    by_sprint: list[BugRateBySprint] = Field(default_factory=list)
    by_issue_type: list[BugRateByIssueType] = Field(default_factory=list)


class MetricsSummary(BaseModel):
    """Headline KPIs for dashboards and reports."""

    project_key: str
    total_issues: int
    done_count: int
    open_count: int
    reopened_count: int
    throughput: int
    median_lead_time_hours: float | None = None
    median_cycle_time_hours: float | None = None
    median_net_cycle_time_hours: float | None = None
    p90_lead_time_hours: float | None = None
    average_active_time_hours: float | None = None
    median_buffer_time_hours: float | None = None
    median_blocked_time_hours: float | None = None
    blocked_issue_percent: float | None = None
    average_waiting_time_hours: float | None = None
    average_net_flow_efficiency_percent: float | None = None
    average_reopens: float = 0.0
    bug_rate_percent: float | None = None


class MetricsDocument(BaseModel):
    """Complete metrics output persisted to cache/metrics.json."""

    schema_version: str = METRICS_SCHEMA_VERSION
    generated_at: datetime = Field(default_factory=utc_now)
    source_timelines_at: datetime | None = None
    source_issues_at: datetime | None = None
    project: ProjectMetrics
    issues: list[IssueMetrics] = Field(default_factory=list)
    summary: MetricsSummary
    bug_analytics: BugAnalytics = Field(default_factory=BugAnalytics)

    @classmethod
    def from_parts(
        cls,
        project: ProjectMetrics,
        issues: list[IssueMetrics],
        *,
        source_timelines_at: datetime | None = None,
        source_issues_at: datetime | None = None,
        bug_analytics: BugAnalytics | None = None,
    ) -> MetricsDocument:
        """Build a document with an auto-generated summary section."""
        summary = MetricsSummary(
            project_key=project.project_key,
            total_issues=project.total_issues,
            done_count=project.done_count,
            open_count=project.open_count,
            reopened_count=project.reopened_count,
            throughput=project.throughput,
            median_lead_time_hours=seconds_to_hours(project.median_lead_time_seconds)
            if project.median_lead_time_seconds is not None
            else None,
            median_cycle_time_hours=seconds_to_hours(project.median_cycle_time_seconds)
            if project.median_cycle_time_seconds is not None
            else None,
            median_net_cycle_time_hours=seconds_to_hours(project.median_net_cycle_time_seconds)
            if project.median_net_cycle_time_seconds is not None
            else None,
            p90_lead_time_hours=seconds_to_hours(project.p90_lead_time_seconds)
            if project.p90_lead_time_seconds is not None
            else None,
            average_active_time_hours=seconds_to_hours(project.average_active_time_seconds)
            if project.average_active_time_seconds is not None
            else None,
            median_buffer_time_hours=seconds_to_hours(project.median_buffer_time_seconds)
            if project.median_buffer_time_seconds is not None
            else None,
            median_blocked_time_hours=seconds_to_hours(project.median_blocked_time_seconds)
            if project.median_blocked_time_seconds is not None
            else None,
            blocked_issue_percent=project.blocked_issue_percent,
            average_waiting_time_hours=seconds_to_hours(project.average_waiting_time_seconds)
            if project.average_waiting_time_seconds is not None
            else None,
            average_net_flow_efficiency_percent=project.average_net_flow_efficiency_percent,
            average_reopens=project.average_reopens,
            bug_rate_percent=project.bug_rate_percent,
        )
        return cls(
            project=project,
            issues=issues,
            summary=summary,
            bug_analytics=bug_analytics or BugAnalytics(
                completed_bugs=project.completed_bugs,
                completed_hotfix=project.completed_hotfix,
                total_bugs=project.total_bugs,
                completed_issues=project.done_count,
                bug_rate_percent=project.bug_rate_percent,
            ),
            source_timelines_at=source_timelines_at,
            source_issues_at=source_issues_at,
        )

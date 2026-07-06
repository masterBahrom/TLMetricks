"""Analytics domain models — output of Phase 4 Analytics Engine."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from jira_analytics.utils.datetime_utils import utc_now


class PeriodCount(BaseModel):
    """Count of completed issues for a time period."""

    period_start: date
    period_label: str
    count: int


class ThroughputTimeline(BaseModel):
    """Completed issues over time at multiple granularities."""

    daily: list[PeriodCount] = Field(default_factory=list)
    weekly: list[PeriodCount] = Field(default_factory=list)
    monthly: list[PeriodCount] = Field(default_factory=list)


class ThroughputDistribution(BaseModel):
    """Distribution of completions by week and month."""

    per_week: list[PeriodCount] = Field(default_factory=list)
    per_month: list[PeriodCount] = Field(default_factory=list)


class WIPSnapshot(BaseModel):
    """Work-in-progress count on a single day."""

    date: date
    active_issue_count: int


class WIPTimeline(BaseModel):
    """Daily WIP (non-terminal issues) over time."""

    daily: list[WIPSnapshot] = Field(default_factory=list)


class AgingIssue(BaseModel):
    """Aging data for a single open issue."""

    issue_key: str
    current_status: str
    aging_seconds: float
    aging_hours: float
    aging_days: float


class AgingAnalytics(BaseModel):
    """Aging statistics for open issues only."""

    top_oldest: list[AgingIssue] = Field(default_factory=list)
    average_seconds: float | None = None
    median_seconds: float | None = None
    p90_seconds: float | None = None
    open_issue_count: int = 0


class FlowEfficiencyEntry(BaseModel):
    """Flow efficiency for a single completed issue."""

    issue_key: str
    active_time_seconds: float
    lead_time_seconds: float
    efficiency_percent: float


class FlowAnalytics(BaseModel):
    """Flow efficiency across the project."""

    average_efficiency_percent: float | None = None
    median_efficiency_percent: float | None = None
    per_issue: list[FlowEfficiencyEntry] = Field(default_factory=list)


class QueueCategoryTotal(BaseModel):
    """Aggregated time spent in a queue category."""

    category: str
    total_seconds: float
    total_hours: float
    average_seconds: float
    average_hours: float
    percent_of_total: float
    issue_count: int


class QueueAnalytics(BaseModel):
    """Time spent in queue, waiting, review, QA, active, and done stages."""

    categories: list[QueueCategoryTotal] = Field(default_factory=list)
    total_seconds: float = 0.0


class StatusDistributionEntry(BaseModel):
    """Average time in a status grouped by workflow type."""

    status: str
    workflow_type: str
    average_seconds: float
    average_hours: float
    issue_count: int


class StatusDistribution(BaseModel):
    """Per-status time distribution."""

    by_status: list[StatusDistributionEntry] = Field(default_factory=list)


class Bottleneck(BaseModel):
    """Detected bottleneck stage."""

    category: str
    status: str
    average_seconds: float
    average_hours: float


class BottleneckAnalytics(BaseModel):
    """Automatically detected bottlenecks."""

    largest_queue: Bottleneck | None = None
    largest_waiting: Bottleneck | None = None
    largest_review: Bottleneck | None = None
    largest_qa: Bottleneck | None = None
    largest_active: Bottleneck | None = None


class ReopenedIssueEntry(BaseModel):
    """Issue with reopen history."""

    issue_key: str
    reopen_count: int


class ReopenAnalytics(BaseModel):
    """Reopen statistics."""

    reopen_percent: float
    average_reopen_count: float
    reopened_issue_count: int
    most_reopened: list[ReopenedIssueEntry] = Field(default_factory=list)


class AnalyticsSummary(BaseModel):
    """Headline analytics summary."""

    project_key: str
    total_issues: int
    completed_issues: int
    open_issues: int
    total_throughput: int
    average_flow_efficiency_percent: float | None = None
    reopen_percent: float = 0.0
    average_aging_hours: float | None = None


class TrendAnalytics(BaseModel):
    """Time-series trend data."""

    throughput: ThroughputTimeline
    wip: WIPTimeline


class DistributionAnalytics(BaseModel):
    """Distribution analytics."""

    throughput: ThroughputDistribution
    status: StatusDistribution


class AnalyticsDocument(BaseModel):
    """Complete analytics output persisted to cache/analytics.json."""

    generated_at: datetime = Field(default_factory=utc_now)
    source_metrics_at: datetime | None = None
    source_timelines_at: datetime | None = None
    project_key: str
    summary: AnalyticsSummary
    trend: TrendAnalytics
    distributions: DistributionAnalytics
    flow: FlowAnalytics
    queues: QueueAnalytics
    bottlenecks: BottleneckAnalytics
    aging: AgingAnalytics
    throughput: ThroughputTimeline

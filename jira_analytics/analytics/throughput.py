"""Throughput timeline and distribution analytics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from jira_analytics.analytics.models import PeriodCount, ThroughputDistribution, ThroughputTimeline
from jira_analytics.models.metrics import IssueMetrics


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _period_label(day: date, granularity: str) -> str:
    if granularity == "daily":
        return day.isoformat()
    if granularity == "weekly":
        start = _week_start(day)
        return f"{start.isoformat()}"
    return day.strftime("%Y-%m")


def _aggregate_completions(
    issues: list[IssueMetrics],
    granularity: str,
) -> list[PeriodCount]:
    counts: dict[date, int] = defaultdict(int)

    for issue in issues:
        if not issue.is_done or issue.done_date is None:
            continue
        done_day = issue.done_date.date()
        if granularity == "daily":
            key = done_day
        elif granularity == "weekly":
            key = _week_start(done_day)
        else:
            key = _month_start(done_day)
        counts[key] += 1

    return [
        PeriodCount(period_start=period_start, period_label=_period_label(period_start, granularity), count=count)
        for period_start, count in sorted(counts.items())
    ]


def compute_throughput_timeline(issues: list[IssueMetrics]) -> ThroughputTimeline:
    """Build daily, weekly, and monthly throughput timelines."""
    return ThroughputTimeline(
        daily=_aggregate_completions(issues, "daily"),
        weekly=_aggregate_completions(issues, "weekly"),
        monthly=_aggregate_completions(issues, "monthly"),
    )


def compute_throughput_distribution(issues: list[IssueMetrics]) -> ThroughputDistribution:
    """Build weekly and monthly throughput distributions."""
    return ThroughputDistribution(
        per_week=_aggregate_completions(issues, "weekly"),
        per_month=_aggregate_completions(issues, "monthly"),
    )


def completion_dates(issues: list[IssueMetrics]) -> list[datetime]:
    return [issue.done_date for issue in issues if issue.is_done and issue.done_date is not None]

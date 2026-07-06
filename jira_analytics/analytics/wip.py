"""WIP (work in progress) timeline analytics."""

from __future__ import annotations

from datetime import datetime

from jira_analytics.analytics.models import WIPSnapshot, WIPTimeline
from jira_analytics.analytics.timeline_utils import date_range, end_of_day, is_wip_at, iter_days
from jira_analytics.analytics.throughput import completion_dates
from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.models.timeline import IssueTimeline


def compute_wip_timeline(
    timelines: dict[str, IssueTimeline],
    issues: list[IssueMetrics],
    workflow: WorkflowConfig,
    reference: datetime,
) -> WIPTimeline:
    """Count non-terminal (WIP) issues for each day in the analysis window."""
    done_dates = completion_dates(issues)
    start, end = date_range(timelines, done_dates, reference)

    daily: list[WIPSnapshot] = []
    for day in iter_days(start, end):
        moment = end_of_day(day)
        count = sum(1 for timeline in timelines.values() if is_wip_at(timeline, moment, workflow))
        daily.append(WIPSnapshot(date=day, active_issue_count=count))

    return WIPTimeline(daily=daily)

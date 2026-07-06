"""Aging analytics for open issues."""

from __future__ import annotations

from datetime import datetime

from jira_analytics.analytics.models import AgingAnalytics, AgingIssue
from jira_analytics.analytics.timeline_utils import current_aging_seconds
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.models.timeline import IssueTimeline
from jira_analytics.utils.stats import percentile, safe_mean, seconds_to_days, seconds_to_hours

TOP_N = 10


def compute_aging(
    issues: list[IssueMetrics],
    timelines: dict[str, IssueTimeline],
    reference: datetime,
) -> AgingAnalytics:
    """Compute aging statistics for open issues only."""
    aging_values: list[AgingIssue] = []

    metrics_by_key = {issue.issue_key: issue for issue in issues}

    for issue_key, timeline in timelines.items():
        metrics = metrics_by_key.get(issue_key)
        if metrics and metrics.is_done:
            continue

        seconds = current_aging_seconds(timeline, reference)
        if seconds is None:
            continue

        current_status = metrics.current_status if metrics else timeline.periods[-1].status_name
        aging_values.append(
            AgingIssue(
                issue_key=issue_key,
                current_status=current_status or "Unknown",
                aging_seconds=seconds,
                aging_hours=seconds_to_hours(seconds),
                aging_days=seconds_to_days(seconds),
            )
        )

    seconds_list = [entry.aging_seconds for entry in aging_values]
    top_oldest = sorted(aging_values, key=lambda entry: entry.aging_seconds, reverse=True)[:TOP_N]

    return AgingAnalytics(
        top_oldest=top_oldest,
        average_seconds=safe_mean(seconds_list),
        median_seconds=percentile(seconds_list, 50),
        p90_seconds=percentile(seconds_list, 90),
        open_issue_count=len(aging_values),
    )

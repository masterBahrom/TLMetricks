"""Bottleneck detection analytics."""

from __future__ import annotations

from collections import defaultdict

from jira_analytics.analytics.models import Bottleneck, BottleneckAnalytics
from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.utils.stats import seconds_to_hours


def _largest_in_category(
    issues: list[IssueMetrics],
    workflow: WorkflowConfig,
    target_category: str,
) -> Bottleneck | None:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for issue in issues:
        for entry in issue.time_in_status:
            category = workflow.queue_category(entry.status)
            if category == "other" and target_category == "waiting":
                category = "waiting"
            if category != target_category:
                continue
            totals[entry.status] += entry.duration_seconds
            counts[entry.status] += 1

    if not totals:
        return None

    status, total = max(totals.items(), key=lambda item: item[1])
    count = counts[status]
    average = total / count
    return Bottleneck(
        category=target_category,
        status=status,
        average_seconds=average,
        average_hours=seconds_to_hours(average),
    )


def compute_bottlenecks(issues: list[IssueMetrics], workflow: WorkflowConfig) -> BottleneckAnalytics:
    """Detect the largest time-consuming stage in each queue category."""
    return BottleneckAnalytics(
        largest_queue=_largest_in_category(issues, workflow, "queue"),
        largest_waiting=_largest_in_category(issues, workflow, "waiting"),
        largest_review=_largest_in_category(issues, workflow, "review"),
        largest_qa=_largest_in_category(issues, workflow, "qa"),
        largest_active=_largest_in_category(issues, workflow, "active"),
    )

"""Status distribution analytics."""

from __future__ import annotations

from collections import defaultdict

from jira_analytics.analytics.models import StatusDistribution, StatusDistributionEntry
from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.utils.stats import seconds_to_hours


def compute_status_distribution(issues: list[IssueMetrics], workflow: WorkflowConfig) -> StatusDistribution:
    """Average time per status grouped by workflow type."""
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    workflow_types: dict[str, str] = {}

    for issue in issues:
        for entry in issue.time_in_status:
            totals[entry.status] += entry.duration_seconds
            counts[entry.status] += 1
            workflow_types[entry.status] = workflow.workflow_type(entry.status)

    entries = [
        StatusDistributionEntry(
            status=status,
            workflow_type=workflow_types[status],
            average_seconds=totals[status] / counts[status],
            average_hours=seconds_to_hours(totals[status] / counts[status]),
            issue_count=counts[status],
        )
        for status in sorted(totals)
    ]

    return StatusDistribution(by_status=entries)

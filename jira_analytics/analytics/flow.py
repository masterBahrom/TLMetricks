"""Flow efficiency analytics."""

from __future__ import annotations

from jira_analytics.analytics.models import FlowAnalytics, FlowEfficiencyEntry
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.utils.stats import percentile, safe_mean


def compute_flow_efficiency(issues: list[IssueMetrics]) -> FlowAnalytics:
    """
    Flow Efficiency = Active Time / Lead Time × 100.

    Computed for completed issues with valid lead time.
    """
    entries: list[FlowEfficiencyEntry] = []
    efficiencies: list[float] = []

    for issue in issues:
        if not issue.is_done:
            continue
        if issue.lead_time_seconds is None or issue.lead_time_seconds <= 0:
            continue

        efficiency = min(100.0, (issue.total_active_time_seconds / issue.lead_time_seconds) * 100.0)
        efficiencies.append(efficiency)
        entries.append(
            FlowEfficiencyEntry(
                issue_key=issue.issue_key,
                active_time_seconds=issue.total_active_time_seconds,
                lead_time_seconds=issue.lead_time_seconds,
                efficiency_percent=round(efficiency, 4),
            )
        )

    return FlowAnalytics(
        average_efficiency_percent=round(safe_mean(efficiencies), 4) if efficiencies else None,
        median_efficiency_percent=round(percentile(efficiencies, 50), 4) if efficiencies else None,
        per_issue=entries,
    )

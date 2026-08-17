"""Blocked-time analytics."""

from __future__ import annotations

from collections import defaultdict

from jira_analytics.analytics.models import BlockedAnalytics, BlockedGroupTotal, BlockedIssueEntry
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.utils.stats import percentile, safe_mean, seconds_to_hours


def compute_blocked_analytics(issues: list[IssueMetrics]) -> BlockedAnalytics:
    """Compute blocked-time rollups from issue metrics."""
    blocked = [issue for issue in issues if issue.blocked_time_seconds > 0]
    durations = [issue.blocked_time_seconds for issue in blocked]

    return BlockedAnalytics(
        total_blocked_issues=len(blocked),
        blocked_percent=round(len(blocked) / len(issues) * 100, 4) if issues else None,
        average_blocked_seconds=safe_mean(durations),
        median_blocked_seconds=percentile(durations, 50),
        p90_blocked_seconds=percentile(durations, 90),
        top_blocked_issues=[
            BlockedIssueEntry(
                issue_key=issue.issue_key,
                blocked_time_seconds=issue.blocked_time_seconds,
                blocked_time_hours=issue.blocked_time_hours,
                current_status=issue.current_status,
                assignee=issue.assignee,
            )
            for issue in sorted(blocked, key=lambda item: item.blocked_time_seconds, reverse=True)[:20]
        ],
        by_current_status=_group_blocked(blocked, lambda issue: issue.current_status or "Unassigned Status"),
        by_assignee=_group_blocked(blocked, lambda issue: issue.assignee or "Unassigned"),
    )


def _group_blocked(
    issues: list[IssueMetrics],
    key_fn,
) -> list[BlockedGroupTotal]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for issue in issues:
        key = key_fn(issue)
        totals[key] += issue.blocked_time_seconds
        counts[key] += 1

    return [
        BlockedGroupTotal(
            name=name,
            total_seconds=total,
            total_hours=seconds_to_hours(total),
            issue_count=counts[name],
        )
        for name, total in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]

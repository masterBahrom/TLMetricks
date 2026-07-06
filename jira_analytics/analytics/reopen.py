"""Reopen analytics."""

from __future__ import annotations

from jira_analytics.analytics.models import ReopenAnalytics, ReopenedIssueEntry
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.utils.stats import safe_mean

TOP_N = 10


def compute_reopen_analytics(issues: list[IssueMetrics]) -> ReopenAnalytics:
    """Compute reopen rate and most reopened issues."""
    total = len(issues)
    reopened = [issue for issue in issues if issue.is_reopened or issue.reopen_count > 0]
    reopen_counts = [float(issue.reopen_count) for issue in issues]

    most_reopened = sorted(
        [
            ReopenedIssueEntry(issue_key=issue.issue_key, reopen_count=issue.reopen_count)
            for issue in issues
            if issue.reopen_count > 0
        ],
        key=lambda entry: entry.reopen_count,
        reverse=True,
    )[:TOP_N]

    reopen_percent = round((len(reopened) / total) * 100, 4) if total else 0.0

    return ReopenAnalytics(
        reopen_percent=reopen_percent,
        average_reopen_count=safe_mean(reopen_counts) or 0.0,
        reopened_issue_count=len(reopened),
        most_reopened=most_reopened,
    )

"""Queue stage time analysis."""

from __future__ import annotations

from collections import defaultdict

from jira_analytics.analytics.models import QueueAnalytics, QueueCategoryTotal
from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.utils.stats import seconds_to_hours

QUEUE_CATEGORIES = ("queue", "waiting", "review", "qa", "active", "done")


def compute_queue_analysis(issues: list[IssueMetrics], workflow: WorkflowConfig) -> QueueAnalytics:
    """Aggregate time spent in queue, waiting, review, QA, active, and done stages."""
    category_totals: dict[str, float] = defaultdict(float)
    category_issue_counts: dict[str, set[str]] = defaultdict(set)

    for issue in issues:
        for entry in issue.time_in_status:
            category = workflow.queue_category(entry.status)
            if category == "other":
                category = "waiting"
            category_totals[category] += entry.duration_seconds
            category_issue_counts[category].add(issue.issue_key)

    grand_total = sum(category_totals.values()) or 1.0
    categories: list[QueueCategoryTotal] = []

    for category in QUEUE_CATEGORIES:
        total = category_totals.get(category, 0.0)
        issue_count = len(category_issue_counts.get(category, set()))
        average = total / issue_count if issue_count else 0.0
        categories.append(
            QueueCategoryTotal(
                category=category,
                total_seconds=total,
                total_hours=seconds_to_hours(total),
                average_seconds=average,
                average_hours=seconds_to_hours(average),
                percent_of_total=round((total / grand_total) * 100, 4),
                issue_count=issue_count,
            )
        )

    return QueueAnalytics(categories=categories, total_seconds=grand_total if grand_total > 1 else sum(category_totals.values()))

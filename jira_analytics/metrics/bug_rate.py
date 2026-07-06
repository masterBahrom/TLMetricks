"""Bug rate analytics from enriched issue metrics."""

from __future__ import annotations

from collections import defaultdict

from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import (
    BugAnalytics,
    BugRateByIssueType,
    BugRateBySprint,
    IssueMetrics,
)


def compute_bug_analytics(issues: list[IssueMetrics], workflow: WorkflowConfig) -> BugAnalytics:
    """Compute bug rate for completed issues."""
    done = [issue for issue in issues if issue.is_done]
    bugs = [issue for issue in done if issue.is_bug or workflow.is_bug_type(issue.issue_type)]

    completed_bugs = sum(
        1 for issue in bugs if (issue.issue_type or "").strip().lower() == "bug"
    )
    completed_hotfix = sum(
        1 for issue in bugs if (issue.issue_type or "").strip().lower() == "hot-fix"
    )
    total_bugs = len(bugs)
    completed_issues = len(done)
    bug_rate = (total_bugs / completed_issues * 100) if completed_issues else None

    by_sprint: dict[str, list[IssueMetrics]] = defaultdict(list)
    for issue in done:
        sprint = issue.sprint or "No Sprint"
        by_sprint[sprint].append(issue)

    sprint_rows: list[BugRateBySprint] = []
    for sprint, sprint_issues in sorted(by_sprint.items()):
        sprint_bugs = sum(
            1
            for issue in sprint_issues
            if issue.is_bug or workflow.is_bug_type(issue.issue_type)
        )
        sprint_rows.append(
            BugRateBySprint(
                sprint=sprint,
                completed_bugs=sprint_bugs,
                completed_issues=len(sprint_issues),
                bug_rate_percent=(sprint_bugs / len(sprint_issues) * 100) if sprint_issues else 0.0,
            )
        )

    by_type: dict[str, list[IssueMetrics]] = defaultdict(list)
    for issue in done:
        by_type[issue.issue_type or "Unknown"].append(issue)

    type_rows = [
        BugRateByIssueType(
            issue_type=issue_type,
            completed_count=len(type_issues),
            bug_count=sum(
                1
                for issue in type_issues
                if issue.is_bug or workflow.is_bug_type(issue.issue_type)
            ),
        )
        for issue_type, type_issues in sorted(by_type.items())
    ]

    return BugAnalytics(
        completed_bugs=completed_bugs,
        completed_hotfix=completed_hotfix,
        total_bugs=total_bugs,
        completed_issues=completed_issues,
        bug_rate_percent=round(bug_rate, 4) if bug_rate is not None else None,
        by_sprint=sprint_rows,
        by_issue_type=type_rows,
    )


def mark_bug_flags(issues: list[IssueMetrics], workflow: WorkflowConfig) -> list[IssueMetrics]:
    """Set is_bug on issues based on issue_type."""
    return [
        issue.model_copy(update={"is_bug": workflow.is_bug_type(issue.issue_type)})
        for issue in issues
    ]

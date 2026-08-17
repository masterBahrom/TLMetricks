"""Table builders for Streamlit dataframes."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from dashboard.filters import FilterState
    from dashboard.loader import DashboardData

from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.utils.stats import percentile


def _flow_efficiency(issue: IssueMetrics, flow_by_key: dict[str, float]) -> float | None:
    if issue.flow_efficiency_percent is not None:
        return issue.flow_efficiency_percent
    return flow_by_key.get(issue.issue_key)


def issues_to_dataframe(
    issues: list[IssueMetrics],
    flow_by_key: dict[str, float],
) -> pd.DataFrame:
    rows = []
    for issue in issues:
        rows.append(
            {
                "Issue": issue.issue_key,
                "Summary": issue.summary or "—",
                "Status": issue.current_status or "—",
                "Assignee": issue.assignee or "—",
                "Priority": issue.priority or "—",
                "Issue Type": issue.issue_type or "—",
                "Lead Time (h)": issue.lead_time_hours,
                "Cycle Time (h)": issue.cycle_time_hours,
                "Net Cycle Time (h)": issue.net_cycle_time_hours,
                "Waiting (h)": issue.waiting_time_hours,
                "Blocked Time (h)": issue.blocked_time_hours,
                "Flow Efficiency (%)": _flow_efficiency(issue, flow_by_key),
                "Net Flow Efficiency (%)": issue.net_flow_efficiency_percent,
                "Reopened": issue.is_reopened or issue.reopen_count > 0,
                "Reopen Count": issue.reopen_count,
                "Story Points": issue.story_points,
                "Sprint": issue.sprint or "—",
                "Labels": ", ".join(issue.labels) if issue.labels else "—",
                "Created": issue.created_date,
                "Done": issue.is_done,
            }
        )
    return pd.DataFrame(rows)


def lead_time_table(issues: list[IssueMetrics]) -> pd.DataFrame:
    rows = sorted(
        [
            {
                "Issue Key": issue.issue_key,
                "Summary": issue.summary or "—",
                "Lead Time (h)": issue.lead_time_hours,
                "Cycle Time (h)": issue.cycle_time_hours,
                "Net Cycle Time (h)": issue.net_cycle_time_hours,
                "Waiting (h)": issue.waiting_time_hours,
                "Blocked Time (h)": issue.blocked_time_hours,
                "Active (h)": issue.total_active_time_hours,
                "Reopened": "Yes" if issue.is_reopened else "No",
                "Status": issue.current_status,
            }
            for issue in issues
            if issue.lead_time_hours is not None
        ],
        key=lambda row: row["Lead Time (h)"] or 0,
        reverse=True,
    )
    return pd.DataFrame(rows)


def top_longest_lead_time(issues: list[IssueMetrics], limit: int = 20) -> pd.DataFrame:
    df = lead_time_table(issues)
    return df.head(limit) if not df.empty else df


def aging_table(data: DashboardData) -> pd.DataFrame:
    metrics_by_key = {issue.issue_key: issue for issue in data.issues}
    rows = []
    for entry in sorted(data.analytics.aging.top_oldest, key=lambda e: e.aging_days, reverse=True):
        issue = metrics_by_key.get(entry.issue_key)
        rows.append(
            {
                "Issue": entry.issue_key,
                "Summary": issue.summary if issue and issue.summary else "—",
                "Status": entry.current_status,
                "Assignee": issue.assignee if issue and issue.assignee else "—",
                "Created": issue.created_date if issue else None,
                "Aging Days": entry.aging_days,
            }
        )
    if not rows:
        rows.append(
            {
                "Issue": "No open issues",
                "Summary": "—",
                "Status": "—",
                "Assignee": "—",
                "Created": None,
                "Aging Days": 0,
            }
        )
    return pd.DataFrame(rows)


def status_analysis_table(data: DashboardData) -> pd.DataFrame:
    """Status table with avg from analytics; median/p90 from per-issue time_in_status."""
    by_status: dict[str, list[float]] = defaultdict(list)
    for issue in data.issues:
        for entry in issue.time_in_status:
            by_status[entry.status].append(entry.hours)

    rows = []
    for entry in data.analytics.distributions.status.by_status:
        hours_list = by_status.get(entry.status, [])
        rows.append(
            {
                "Status": entry.status,
                "Category": entry.workflow_type,
                "Average (h)": entry.average_hours,
                "Median (h)": percentile(hours_list, 50) if hours_list else None,
                "P90 (h)": percentile(hours_list, 90) if hours_list else None,
                "Count": entry.issue_count,
            }
        )
    return pd.DataFrame(rows)


def reopened_table(issues: list[IssueMetrics]) -> pd.DataFrame:
    reopened = [
        issue
        for issue in issues
        if issue.is_reopened or issue.reopen_count > 0
    ]
    rows = [
        {
            "Issue": issue.issue_key,
            "Summary": issue.summary or "—",
            "Reopen Count": issue.reopen_count,
            "Lead Time (h)": issue.lead_time_hours,
            "Current Status": issue.current_status,
            "Assignee": issue.assignee or "—",
        }
        for issue in sorted(reopened, key=lambda i: i.reopen_count, reverse=True)
    ]
    if not rows:
        rows.append(
            {
                "Issue": "No reopened issues",
                "Summary": "—",
                "Reopen Count": 0,
                "Lead Time (h)": None,
                "Current Status": "—",
                "Assignee": "—",
            }
        )
    return pd.DataFrame(rows)


def explorer_table(
    data: DashboardData,
    filters: FilterState,
    search: str,
) -> pd.DataFrame:
    from dashboard.filters import FilterState as FS, apply_filters

    state = FS(
        project=filters.project,
        date_start=filters.date_start,
        date_end=filters.date_end,
        statuses=filters.statuses,
        assignees=filters.assignees,
        issue_types=filters.issue_types,
        priorities=filters.priorities,
        sprints=filters.sprints,
        workflow_categories=filters.workflow_categories,
        terminal_statuses=filters.terminal_statuses,
        reopened_only=filters.reopened_only,
        open_only=filters.open_only,
        search=search,
    )
    issues = apply_filters(data, state)
    return issues_to_dataframe(issues, data.flow_by_key)


def throughput_dataframe(data: DashboardData, granularity: str) -> pd.DataFrame:
    buckets = getattr(data.analytics.throughput, granularity, [])
    return pd.DataFrame(
        [{"Period": bucket.period_label, "Count": bucket.count} for bucket in buckets]
    )

"""Sidebar filters — subset issues without recalculating analytics aggregates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dashboard.loader import DashboardData

from jira_analytics.models.metrics import IssueMetrics


@dataclass
class FilterState:
    """Active sidebar filter selections."""

    project: str = "All"
    date_start: date | None = None
    date_end: date | None = None
    statuses: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    issue_types: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    sprints: list[str] = field(default_factory=list)
    workflow_categories: list[str] = field(default_factory=list)
    terminal_statuses: list[str] = field(default_factory=list)
    reopened_only: bool = False
    open_only: bool = False
    search: str = ""

    @property
    def is_active(self) -> bool:
        return any(
            [
                self.date_start is not None,
                self.date_end is not None,
                bool(self.statuses),
                bool(self.assignees),
                bool(self.issue_types),
                bool(self.priorities),
                bool(self.sprints),
                bool(self.workflow_categories),
                bool(self.terminal_statuses),
                self.reopened_only,
                self.open_only,
                bool(self.search.strip()),
            ]
        )


def _issue_created(issue: IssueMetrics) -> date | None:
    if issue.created_date is None:
        return None
    return issue.created_date.date() if isinstance(issue.created_date, datetime) else issue.created_date


def _distinct(values: list[str | None]) -> list[str]:
    return sorted({value for value in values if value})


def available_statuses(data: DashboardData) -> list[str]:
    return _distinct([issue.current_status for issue in data.issues])


def available_assignees(data: DashboardData) -> list[str]:
    return _distinct([issue.assignee for issue in data.issues])


def available_issue_types(data: DashboardData) -> list[str]:
    return _distinct([issue.issue_type for issue in data.issues])


def available_priorities(data: DashboardData) -> list[str]:
    return _distinct([issue.priority for issue in data.issues])


def available_sprints(data: DashboardData) -> list[str]:
    return _distinct([issue.sprint for issue in data.issues])


def available_workflow_categories(data: DashboardData) -> list[str]:
    categories = {
        data.workflow.queue_category(issue.current_status or "")
        for issue in data.issues
        if issue.current_status
    }
    return sorted(categories)


def available_terminal_statuses(data: DashboardData) -> list[str]:
    terminal = {s for s in data.workflow.terminal_statuses + data.workflow.cancelled_statuses}
    present = {
        issue.current_status
        for issue in data.issues
        if issue.current_status and issue.is_done
    }
    return sorted(terminal & present)


def apply_filters(data: DashboardData, filters: FilterState) -> list[IssueMetrics]:
    """Return issues matching sidebar filters (client-side subset only)."""
    result: list[IssueMetrics] = []
    for issue in data.issues:
        if filters.statuses and (issue.current_status or "") not in filters.statuses:
            continue
        if filters.assignees and (issue.assignee or "") not in filters.assignees:
            continue
        if filters.issue_types and (issue.issue_type or "") not in filters.issue_types:
            continue
        if filters.priorities and (issue.priority or "") not in filters.priorities:
            continue
        if filters.sprints and (issue.sprint or "") not in filters.sprints:
            continue
        if filters.workflow_categories:
            category = data.workflow.queue_category(issue.current_status or "")
            if category not in filters.workflow_categories:
                continue
        if filters.terminal_statuses and issue.is_done:
            if (issue.current_status or "") not in filters.terminal_statuses:
                continue
        if filters.reopened_only and not (issue.is_reopened or issue.reopen_count > 0):
            continue
        if filters.open_only and issue.is_done:
            continue

        created = _issue_created(issue)
        if filters.date_start and created and created < filters.date_start:
            continue
        if filters.date_end and created and created > filters.date_end:
            continue

        if filters.search.strip():
            needle = filters.search.strip().lower()
            haystack = " ".join(
                [
                    issue.issue_key,
                    issue.summary or "",
                    issue.current_status or "",
                    issue.assignee or "",
                ]
            ).lower()
            if needle not in haystack:
                continue

        result.append(issue)
    return result


def render_filters(data: DashboardData) -> FilterState:
    """Render sidebar filters and return current state. Requires Streamlit."""
    import streamlit as st

    st.sidebar.header("Filters")

    theme = st.sidebar.radio("Theme", ["Light", "Dark"], horizontal=True, key="dashboard_theme")
    st.session_state["plotly_template"] = "plotly_dark" if theme == "Dark" else "plotly_white"

    project = st.sidebar.selectbox("Project", [data.project_key], disabled=True)

    created_dates = [_issue_created(issue) for issue in data.issues]
    created_dates = [d for d in created_dates if d is not None]
    min_date = min(created_dates) if created_dates else date.today()
    max_date = max(created_dates) if created_dates else date.today()

    date_range = st.sidebar.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    date_start, date_end = (date_range if isinstance(date_range, tuple) else (date_range, date_range))

    statuses = st.sidebar.multiselect("Status", available_statuses(data))
    assignees = st.sidebar.multiselect("Assignee", available_assignees(data))
    issue_types = st.sidebar.multiselect("Issue Type", available_issue_types(data))
    priorities = st.sidebar.multiselect("Priority", available_priorities(data))
    sprints = st.sidebar.multiselect("Sprint", available_sprints(data))

    workflow_categories = st.sidebar.multiselect(
        "Workflow Category",
        available_workflow_categories(data),
    )
    terminal_statuses = st.sidebar.multiselect(
        "Terminal Status",
        available_terminal_statuses(data),
    )
    reopened_only = st.sidebar.checkbox("Reopened Only")
    open_only = st.sidebar.checkbox("Open Only")

    return FilterState(
        project=project,
        date_start=date_start,
        date_end=date_end,
        statuses=statuses,
        assignees=assignees,
        issue_types=issue_types,
        priorities=priorities,
        sprints=sprints,
        workflow_categories=workflow_categories,
        terminal_statuses=terminal_statuses,
        reopened_only=reopened_only,
        open_only=open_only,
    )


def render_explorer_search() -> str:
    """Search box for Issue Explorer page."""
    import streamlit as st

    return st.text_input("Search issues", placeholder="Issue key, summary, status, assignee…")

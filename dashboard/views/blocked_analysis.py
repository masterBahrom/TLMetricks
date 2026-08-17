"""Blocked-time analysis page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState
from dashboard.loader import DashboardData


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Blocked Analysis")
    if filters.is_active:
        st.caption("Blocked analytics use the full metrics dataset.")

    project = data.metrics.project
    blocked_hours = [issue.blocked_time_hours for issue in data.issues if issue.blocked_time_seconds > 0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Median Blocked Time",
        f"{project.median_blocked_time_seconds / 3600:.1f}h"
        if project.median_blocked_time_seconds is not None
        else "N/A",
    )
    col2.metric(
        "Average Blocked Time",
        f"{project.average_blocked_time_seconds / 3600:.1f}h"
        if project.average_blocked_time_seconds is not None
        else "N/A",
    )
    col3.metric(
        "P90 Blocked Time",
        f"{project.p90_blocked_time_seconds / 3600:.1f}h"
        if project.p90_blocked_time_seconds is not None
        else "N/A",
    )
    col4.metric(
        "Blocked Issue %",
        f"{project.blocked_issue_percent:.1f}%" if project.blocked_issue_percent is not None else "N/A",
    )

    if blocked_hours:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(charts.histogram(blocked_hours, "Blocked Time Distribution"), use_container_width=True)
        with right:
            st.plotly_chart(charts.box_plot(blocked_hours, "Blocked Time Spread"), use_container_width=True)

    top_rows = [
        {
            "Issue": entry.issue_key,
            "Blocked (h)": round(entry.blocked_time_hours, 2),
            "Status": entry.current_status or "—",
            "Assignee": entry.assignee or "—",
        }
        for entry in data.analytics.blocked.top_blocked_issues
    ]
    st.subheader("Top 20 Blocked Issues")
    st.dataframe(pd.DataFrame(top_rows), use_container_width=True, hide_index=True)

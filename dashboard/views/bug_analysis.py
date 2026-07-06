"""Bug Analysis — bug rate and distribution for TL workflow."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState
from dashboard.loader import DashboardData


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Bug Analysis")
    if filters.is_active:
        st.info("Bug analytics reflect full project metrics. Filters do not apply to this page.")

    bugs = data.metrics.bug_analytics
    project = data.metrics.project

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bug Count", bugs.completed_bugs)
    col2.metric("HOT-FIX Count", bugs.completed_hotfix)
    col3.metric("Total Bugs", bugs.total_bugs)
    rate = bugs.bug_rate_percent or project.bug_rate_percent
    col4.metric("Bug %", f"{rate:.1f}%" if rate is not None else "N/A")

    if bugs.by_sprint:
        st.subheader("Bug Rate by Sprint")
        sprint_df = pd.DataFrame(
            [
                {
                    "Sprint": row.sprint,
                    "Completed Bugs": row.completed_bugs,
                    "Completed Issues": row.completed_issues,
                    "Bug %": round(row.bug_rate_percent, 1),
                }
                for row in bugs.by_sprint
                if row.completed_issues > 0
            ]
        )
        if not sprint_df.empty:
            st.plotly_chart(
                charts.line_chart(
                    sprint_df["Sprint"].tolist(),
                    sprint_df["Bug %"].tolist(),
                    "Bug Rate Trend by Sprint",
                    "Sprint",
                    "Bug %",
                ),
                use_container_width=True,
            )
            st.dataframe(sprint_df, use_container_width=True, hide_index=True)

    if bugs.by_issue_type:
        st.subheader("Distribution by Issue Type")
        type_df = pd.DataFrame(
            [
                {
                    "Issue Type": row.issue_type,
                    "Completed": row.completed_count,
                    "Bugs": row.bug_count,
                    "Bug %": round(row.bug_count / row.completed_count * 100, 1)
                    if row.completed_count
                    else 0.0,
                }
                for row in bugs.by_issue_type
            ]
        )
        st.plotly_chart(
            charts.bar_chart(
                type_df["Issue Type"].tolist(),
                type_df["Bugs"].tolist(),
                "Bugs by Issue Type",
                "Issue Type",
                "Count",
            ),
            use_container_width=True,
        )
        st.dataframe(type_df, use_container_width=True, hide_index=True)

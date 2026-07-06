"""Page 8 — Reopened Issues."""

from __future__ import annotations

import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState, apply_filters
from dashboard.loader import DashboardData
from dashboard.tables import reopened_table


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Reopened Issues")
    issues = apply_filters(data, filters)
    reopened = [issue for issue in issues if issue.is_reopened or issue.reopen_count > 0]

    avg_reopen = data.metrics.project.average_reopens
    st.metric("Average Reopen Count", f"{avg_reopen:.2f}")
    st.metric("Reopen %", f"{data.analytics.summary.reopen_percent:.1f}%")

    if reopened:
        counts = [issue.reopen_count for issue in reopened]
        keys = [issue.issue_key for issue in reopened]
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(charts.bar_chart(keys, counts, "Reopen Count by Issue", "Issue", "Count"), use_container_width=True)
        with col2:
            st.plotly_chart(charts.histogram(counts, "Reopen Distribution", "Reopen Count"), use_container_width=True)

        lead_hours = [issue.lead_time_hours or 0 for issue in reopened]
        created_labels = [issue.issue_key for issue in reopened]
        st.plotly_chart(
            charts.scatter(list(range(len(lead_hours))), lead_hours, created_labels, "Reopened Issues Timeline", "Index", "Lead Time (h)"),
            use_container_width=True,
        )
    else:
        st.info("No reopened issues in the current selection.")

    st.dataframe(reopened_table(issues), use_container_width=True, hide_index=True)

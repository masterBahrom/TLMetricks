"""Page 2 — Lead Time."""

from __future__ import annotations

import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState, apply_filters
from dashboard.loader import DashboardData
from dashboard.tables import lead_time_table, top_longest_lead_time


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Lead Time")
    issues = apply_filters(data, filters)
    if filters.is_active and not issues:
        st.warning("No matching issues for the current filters.")
        return

    lead_hours = [issue.lead_time_hours for issue in issues if issue.lead_time_hours is not None]
    cycle_hours = [issue.cycle_time_hours for issue in issues if issue.cycle_time_hours is not None]

    if not lead_hours:
        st.info("No lead time data available for the current selection.")
        st.dataframe(lead_time_table(issues), use_container_width=True, hide_index=True)
        return

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(charts.histogram(lead_hours, "Lead Time Distribution"), use_container_width=True)
    with col2:
        st.plotly_chart(charts.box_plot(lead_hours, "Lead Time Box Plot"), use_container_width=True)

    if cycle_hours:
        paired = [
            (issue.cycle_time_hours, issue.lead_time_hours, issue.issue_key)
            for issue in issues
            if issue.cycle_time_hours is not None and issue.lead_time_hours is not None
        ]
        if paired:
            st.plotly_chart(
                charts.scatter(
                    [p[0] for p in paired],
                    [p[1] for p in paired],
                    [p[2] for p in paired],
                    "Cycle vs Lead Time",
                    "Cycle Time (h)",
                    "Lead Time (h)",
                ),
                use_container_width=True,
            )

    st.subheader("Top 20 Longest Lead Time")
    st.dataframe(top_longest_lead_time(issues, 20), use_container_width=True, hide_index=True)

    st.subheader("Per Issue")
    st.dataframe(lead_time_table(issues), use_container_width=True, hide_index=True)

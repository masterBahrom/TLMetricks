"""Page 4 — Flow Analysis."""

from __future__ import annotations

import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState
from dashboard.loader import DashboardData


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Flow Analysis")
    if filters.is_active:
        st.caption("Flow metrics are sourced from analytics.json (full dataset).")

    flow = data.analytics.flow
    project = data.metrics.project
    totals = {
        "Active": sum(issue.total_active_time_seconds for issue in data.issues),
        "Buffer": sum(issue.buffer_time_seconds for issue in data.issues),
        "Blocked": sum(issue.blocked_time_seconds for issue in data.issues),
        "Waiting/Other": sum(issue.waiting_time_seconds for issue in data.issues),
    }

    col1, col2, col3 = st.columns(3)
    col1.metric("Gross Flow Efficiency (avg)", f"{flow.average_efficiency_percent:.1f}%" if flow.average_efficiency_percent else "N/A")
    col2.metric(
        "Net Flow Efficiency (avg)",
        f"{project.average_net_flow_efficiency_percent:.1f}%"
        if project.average_net_flow_efficiency_percent is not None
        else "N/A",
    )
    col3.metric("Total Blocked Time (h)", f"{totals['Blocked'] / 3600:.1f}")

    total_seconds = sum(totals.values())
    labels = [label for label, seconds in totals.items() if seconds > 0]
    values = [seconds / total_seconds * 100 for seconds in totals.values() if seconds > 0] if total_seconds else []

    if labels:
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(charts.pie_chart(labels, values, "Flow Mix (%)"), use_container_width=True)
        with col_b:
            st.plotly_chart(
                charts.bar_chart(labels, values, "Category Share (%)", "Category", "Percent"),
                use_container_width=True,
            )

    rows = []
    for label, seconds in totals.items():
        if seconds <= 0:
            continue
        rows.append(
            {
                "Category": label,
                "Percent": f"{seconds / total_seconds * 100:.1f}%" if total_seconds else "0.0%",
                "Total Hours": f"{seconds / 3600:.1f}",
                "Issues": sum(
                    1
                    for issue in data.issues
                    if {
                        "Active": issue.total_active_time_seconds,
                        "Buffer": issue.buffer_time_seconds,
                        "Blocked": issue.blocked_time_seconds,
                        "Waiting/Other": issue.waiting_time_seconds,
                    }[label]
                    > 0
                ),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

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
    queues = {entry.category: entry for entry in data.analytics.queues.categories}

    col1, col2, col3 = st.columns(3)
    col1.metric("Flow Efficiency (avg)", f"{flow.average_efficiency_percent:.1f}%" if flow.average_efficiency_percent else "N/A")
    col2.metric("Flow Efficiency (median)", f"{flow.median_efficiency_percent:.1f}%" if flow.median_efficiency_percent else "N/A")
    col3.metric("Total Flow Time (h)", f"{data.analytics.queues.total_seconds / 3600:.1f}")

    labels: list[str] = []
    values: list[float] = []
    mapping = [
        ("Queue", "queue"),
        ("Waiting", "waiting"),
        ("QA", "qa"),
        ("Review", "review"),
        ("Development", "active"),
        ("Done", "done"),
    ]
    for label, key in mapping:
        entry = queues.get(key)
        if entry:
            labels.append(label)
            values.append(entry.percent_of_total)

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
    for label, key in mapping:
        entry = queues.get(key)
        if entry:
            rows.append(
                {
                    "Category": label,
                    "Percent": f"{entry.percent_of_total:.1f}%",
                    "Total Hours": f"{entry.total_hours:.1f}",
                    "Issues": entry.issue_count,
                }
            )
    st.dataframe(rows, use_container_width=True, hide_index=True)

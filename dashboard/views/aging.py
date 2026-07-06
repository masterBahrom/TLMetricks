"""Page 5 — Aging."""

from __future__ import annotations

import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState
from dashboard.loader import DashboardData
from dashboard.tables import aging_table


def _aging_buckets(data: DashboardData) -> dict[str, int]:
    buckets = {"0-7": 0, "8-14": 0, "15-30": 0, "30+": 0}
    for entry in data.analytics.aging.top_oldest:
        days = entry.aging_days
        if days <= 7:
            buckets["0-7"] += 1
        elif days <= 14:
            buckets["8-14"] += 1
        elif days <= 30:
            buckets["15-30"] += 1
        else:
            buckets["30+"] += 1
    return buckets


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Aging")
    aging = data.analytics.aging

    col1, col2, col3 = st.columns(3)
    col1.metric("Open Issues", aging.open_issue_count)
    avg_days = aging.average_seconds / 86400 if aging.average_seconds else None
    p90_days = aging.p90_seconds / 86400 if aging.p90_seconds else None
    col2.metric("Average Aging", f"{avg_days:.1f}d" if avg_days else "N/A")
    col3.metric("P90 Aging", f"{p90_days:.1f}d" if p90_days else "N/A")

    buckets = _aging_buckets(data)
    labels = list(buckets.keys())
    counts = list(buckets.values())

    col_a, col_b = st.columns(2)
    with col_a:
        if aging.open_issue_count > 0:
            days = [entry.aging_days for entry in data.analytics.aging.top_oldest]
            st.plotly_chart(charts.histogram(days, "Aging Histogram", "Days"), use_container_width=True)
        else:
            st.info("No open issues to chart.")
    with col_b:
        st.plotly_chart(
            charts.bar_chart(labels, counts, "Aging Buckets", "Bucket", "Issues"),
            use_container_width=True,
        )

    st.subheader("Top Oldest Open Issues")
    st.dataframe(aging_table(data), use_container_width=True, hide_index=True)

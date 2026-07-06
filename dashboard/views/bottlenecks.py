"""Page 7 — Bottlenecks."""

from __future__ import annotations

import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState
from dashboard.loader import DashboardData


def _rows(data: DashboardData) -> list[dict]:
    bn = data.analytics.bottlenecks
    mapping = [
        ("Queue", bn.largest_queue),
        ("Waiting", bn.largest_waiting),
        ("Review", bn.largest_review),
        ("QA", bn.largest_qa),
    ]
    rows = []
    for category, bottleneck in mapping:
        if bottleneck:
            rows.append(
                {
                    "Category": category,
                    "Status": bottleneck.status,
                    "Average Hours": bottleneck.average_hours,
                }
            )
        else:
            rows.append({"Category": category, "Status": "N/A", "Average Hours": 0.0})
    return rows


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Bottlenecks")
    rows = _rows(data)

    st.plotly_chart(
        charts.bar_chart(
            [row["Category"] for row in rows],
            [row["Average Hours"] for row in rows],
            "Bottleneck Average Time",
            "Category",
            "Hours",
        ),
        use_container_width=True,
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.subheader("Detected Bottlenecks (analytics.json)")
    bn = data.analytics.bottlenecks
    detail = [
        ("Top Queue", bn.largest_queue),
        ("Top Waiting", bn.largest_waiting),
        ("Top Review", bn.largest_review),
        ("Top QA", bn.largest_qa),
    ]
    for label, bottleneck in detail:
        if bottleneck:
            st.write(f"**{label}:** {bottleneck.status} — {bottleneck.average_hours:.1f}h average")

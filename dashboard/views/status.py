"""Page 6 — Status Analysis."""

from __future__ import annotations

import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState
from dashboard.loader import DashboardData
from dashboard.tables import status_analysis_table


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Status Analysis")
    if filters.is_active:
        st.caption("Status averages from analytics.json; median/P90 from cached per-issue time_in_status.")

    df = status_analysis_table(data)
    if df.empty:
        st.info("No status distribution data available.")
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    st.plotly_chart(
        charts.bar_chart(df["Status"].tolist(), df["Average (h)"].tolist(), "Average Time per Status", "Status", "Hours"),
        use_container_width=True,
    )

    metrics = ["Average (h)", "Median (h)", "P90 (h)"]
    z = []
    for metric in metrics:
        z.append([float(v) if v is not None else 0.0 for v in df[metric].tolist()])

    st.plotly_chart(
        charts.heatmap(z, metrics, df["Status"].tolist(), "Status Time Heatmap"),
        use_container_width=True,
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

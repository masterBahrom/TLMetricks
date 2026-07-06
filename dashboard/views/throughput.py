"""Page 3 — Throughput."""

from __future__ import annotations

import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState
from dashboard.loader import DashboardData
from dashboard.tables import throughput_dataframe


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Throughput")
    if filters.is_active:
        st.caption("Throughput timelines are sourced from analytics.json (full dataset).")

    tab_daily, tab_weekly, tab_monthly = st.tabs(["Daily", "Weekly", "Monthly"])

    for tab, granularity in zip([tab_daily, tab_weekly, tab_monthly], ["daily", "weekly", "monthly"], strict=True):
        df = throughput_dataframe(data, granularity)
        with tab:
            if df.empty:
                st.info(f"No {granularity} throughput data.")
                continue
            st.plotly_chart(
                charts.bar_chart(df["Period"].tolist(), df["Count"].tolist(), f"{granularity.title()} Throughput", "Period", "Issues"),
                use_container_width=True,
            )
            counts = df["Count"].tolist()
            rolling = charts.rolling_average(counts, window=3)
            trend_x = [label for label, value in zip(df["Period"], rolling, strict=True) if value is not None]
            trend_y = [value for value in rolling if value is not None]
            if trend_y:
                st.plotly_chart(
                    charts.line_chart(trend_x, trend_y, f"{granularity.title()} Rolling Average (3-period)"),
                    use_container_width=True,
                )
            st.dataframe(df, use_container_width=True, hide_index=True)

    summary = data.analytics.summary
    st.metric("Total Throughput", summary.total_throughput)

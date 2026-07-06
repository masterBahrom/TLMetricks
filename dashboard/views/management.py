"""Page 10 — Management Insights."""

from __future__ import annotations

import streamlit as st

from dashboard.filters import FilterState
from dashboard.insights import generate_insights
from dashboard.loader import DashboardData


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Management Insights")
    st.caption("Deterministic observations from analytics.json and metrics.json — no AI.")

    if filters.is_active:
        st.info("Insights reflect the full dataset.")

    for text in generate_insights(data):
        st.markdown(f"- {text}")

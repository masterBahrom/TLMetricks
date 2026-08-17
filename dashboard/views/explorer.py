"""Page 9 — Issue Explorer."""

from __future__ import annotations

import streamlit as st

from dashboard.filters import FilterState, render_explorer_search
from dashboard.loader import DashboardData
from dashboard.tables import explorer_table


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Issue Explorer")
    search = render_explorer_search()
    df = explorer_table(data, filters, search)
    if df.empty or (filters.is_active and len(df) == 0):
        st.warning("No matching issues.")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Lead Time (h)": st.column_config.NumberColumn(format="%.1f"),
            "Cycle Time (h)": st.column_config.NumberColumn(format="%.1f"),
            "Net Cycle Time (h)": st.column_config.NumberColumn(format="%.1f"),
            "Waiting (h)": st.column_config.NumberColumn(format="%.1f"),
            "Blocked Time (h)": st.column_config.NumberColumn(format="%.1f"),
            "Flow Efficiency (%)": st.column_config.NumberColumn(format="%.1f"),
            "Net Flow Efficiency (%)": st.column_config.NumberColumn(format="%.1f"),
            "Reopened": st.column_config.CheckboxColumn(),
        },
    )

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, file_name=f"{data.project_key}_issues.csv", mime="text/csv")

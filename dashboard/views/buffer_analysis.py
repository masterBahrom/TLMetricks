"""Buffer Analysis — queue/wait time across the TL workflow."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard.filters import FilterState, apply_filters
from dashboard.loader import DashboardData


def _top_buffer_issues(issues, limit: int = 20) -> pd.DataFrame:
    done = [issue for issue in issues if issue.is_done and issue.buffer_time_hours > 0]
    done.sort(key=lambda i: i.buffer_time_seconds, reverse=True)
    rows = [
        {
            "Issue": issue.issue_key,
            "Summary": issue.summary or "",
            "Buffer (h)": round(issue.buffer_time_hours, 2),
            "Lead (h)": round(issue.lead_time_hours, 2) if issue.lead_time_hours else None,
            "Active (h)": round(issue.total_active_time_hours, 2),
            "Flow Efficiency (%)": issue.flow_efficiency_percent,
        }
        for issue in done[:limit]
    ]
    return pd.DataFrame(rows)


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Buffer Analysis")
    st.caption(
        "Buffer = Backlog + To Do + Ready for QA + Ready for Deployment "
        "(time when nobody is actively working)."
    )

    project = data.metrics.project
    issues = apply_filters(data, filters)
    buffer_hours = [issue.buffer_time_hours for issue in issues if issue.is_done and issue.buffer_time_hours > 0]

    col1, col2, col3 = st.columns(3)
    avg_h = project.average_buffer_time_seconds / 3600 if project.average_buffer_time_seconds else None
    med_h = project.median_buffer_time_seconds / 3600 if project.median_buffer_time_seconds else None
    p90_h = project.p90_buffer_time_seconds / 3600 if project.p90_buffer_time_seconds else None
    col1.metric("Average Buffer", f"{avg_h:.1f}h" if avg_h is not None else "N/A")
    col2.metric("Median Buffer", f"{med_h:.1f}h" if med_h is not None else "N/A")
    col3.metric("P90 Buffer", f"{p90_h:.1f}h" if p90_h is not None else "N/A")

    if not buffer_hours:
        st.info("No completed issues with buffer time for the current selection.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.histogram(buffer_hours, "Buffer Time Distribution"), use_container_width=True)
    with c2:
        st.plotly_chart(charts.box_plot(buffer_hours, "Buffer Time Box Plot"), use_container_width=True)

    st.subheader("Top 20 Issues with Largest Buffer")
    st.dataframe(_top_buffer_issues(issues), use_container_width=True, hide_index=True)

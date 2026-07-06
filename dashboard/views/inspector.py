"""Issue Metric Inspector — validate per-issue metric calculations."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.filters import FilterState
from dashboard.loader import DashboardData


def _category_style(category: str) -> str:
    if category == "active":
        return "background-color: #d4edda"
    if category == "buffer":
        return "background-color: #fff3cd"
    if category == "terminal":
        return "background-color: #cce5ff"
    return ""


def _find_issue(data: DashboardData, key: str):
    normalized = key.strip().upper()
    for issue in data.issues:
        if issue.issue_key.upper() == normalized:
            return issue
    return None


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Issue Metric Inspector")
    st.caption("Search by issue key to validate Lead, Cycle, Active, Buffer, and Flow Efficiency.")

    default_key = "TL-50"
    query = st.text_input("Issue Key", value=default_key, placeholder="TL-50").strip()
    if not query:
        st.info("Enter an issue key to inspect metrics.")
        return

    issue = _find_issue(data, query)
    if issue is None:
        st.warning(f"Issue {query} not found in metrics.json.")
        return

    meta1, meta2, meta3 = st.columns(3)
    meta1.metric("Created", issue.created_date.strftime("%Y-%m-%d %H:%M") if issue.created_date else "N/A")
    resolved = issue.resolution_date or issue.done_date
    meta2.metric("Resolved", resolved.strftime("%Y-%m-%d %H:%M") if resolved else "Open")
    meta3.metric("Terminal Status", issue.current_status if issue.is_done else "N/A")

    if issue.status_periods:
        st.subheader("Timeline")
        rows = []
        for period in issue.status_periods:
            rows.append(
                {
                    "Status": period.status,
                    "Category": period.category,
                    "Entered": period.entered_at.strftime("%Y-%m-%d %H:%M"),
                    "Left": period.left_at.strftime("%Y-%m-%d %H:%M") if period.left_at else "—",
                    "Duration (h)": round(period.hours, 2),
                }
            )
        timeline_df = pd.DataFrame(rows)

        def _highlight(row):
            return [_category_style(row["Category"])] * len(row)

        st.dataframe(
            timeline_df.style.apply(_highlight, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No status periods recorded for this issue.")

    st.subheader("Computed Metrics")
    m1, m2, m3 = st.columns(3)
    m1.metric("Lead Time", f"{issue.lead_time_hours:.1f}h" if issue.lead_time_hours else "N/A")
    m2.metric("Cycle Time", f"{issue.cycle_time_hours:.1f}h" if issue.cycle_time_hours else "N/A")
    m3.metric("Active Time", f"{issue.total_active_time_hours:.1f}h")

    m4, m5, m6 = st.columns(3)
    m4.metric("Buffer Time", f"{issue.buffer_time_hours:.1f}h")
    fe = issue.flow_efficiency_percent
    m5.metric("Flow Efficiency", f"{fe:.1f}%" if fe is not None else "N/A")
    m6.metric("Bug?", "Yes" if issue.is_bug else "No")

    if issue.is_done and issue.lead_time_seconds:
        accounted = issue.buffer_time_seconds + issue.total_active_time_seconds + issue.terminal_time_seconds
        delta = abs(accounted - issue.lead_time_seconds)
        if delta > 2:
            st.warning(
                f"Buffer + Active + Terminal = {accounted / 3600:.1f}h vs Lead = "
                f"{issue.lead_time_hours:.1f}h (Δ {delta / 3600:.1f}h)"
            )
        else:
            st.success("Buffer + Active + Terminal ≈ Lead Time (within tolerance).")

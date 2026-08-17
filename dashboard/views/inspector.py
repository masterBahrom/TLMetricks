"""Issue Metric Inspector — validate per-issue metric calculations."""

from __future__ import annotations

from datetime import timedelta

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


def _merge_intervals(intervals):
    valid = sorted((start, end) for start, end in intervals if end and end > start)
    if not valid:
        return []
    merged = [valid[0]]
    for start, end in valid[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _duration_hours(start, end) -> float:
    return round((end - start).total_seconds() / 3600, 2)


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
    timeline = data.timelines.timelines.get(issue.issue_key)

    meta1, meta2, meta3 = st.columns(3)
    meta1.metric("Created", issue.created_date.strftime("%Y-%m-%d %H:%M") if issue.created_date else "N/A")
    resolved = issue.resolution_date or issue.done_date
    meta2.metric("Resolved", resolved.strftime("%Y-%m-%d %H:%M") if resolved else "Open")
    meta3.metric("Terminal Status", issue.current_status if issue.is_done else "N/A")

    if issue.status_periods:
        st.subheader("Status Timeline")
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

    if timeline is not None:
        st.subheader("Flagged Timeline")
        flagged_rows = [
            {
                "Flag Start": period.started_at.strftime("%Y-%m-%d %H:%M"),
                "Flag End": period.ended_at.strftime("%Y-%m-%d %H:%M"),
                "Duration (h)": round(period.duration_seconds / 3600, 2),
                "Open": "Yes" if period.is_open else "No",
            }
            for period in timeline.flagged_periods
        ]
        if flagged_rows:
            st.dataframe(pd.DataFrame(flagged_rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No Jira Flagged periods recorded.")

        blocked_status_rows = [
            {
                "Status": period.status_name,
                "Started": period.entered_at.strftime("%Y-%m-%d %H:%M"),
                "Ended": period.left_at.strftime("%Y-%m-%d %H:%M") if period.left_at else "—",
                "Duration (h)": round(period.duration_hours, 2),
            }
            for period in timeline.periods
            if period.status_name.strip().lower() == "blocked"
        ]
        st.subheader("Blocked Status Intervals")
        if blocked_status_rows:
            st.dataframe(pd.DataFrame(blocked_status_rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No literal Blocked status intervals recorded.")

        first_terminal = next((period.entered_at for period in timeline.periods if period.is_done), None)
        intervals = []
        for period in timeline.flagged_periods:
            end = min(period.ended_at, first_terminal) if first_terminal else period.ended_at
            if end > period.started_at:
                intervals.append((period.started_at, end))
        for period in timeline.periods:
            if period.status_name.strip().lower() != "blocked":
                continue
            end = period.left_at or (period.entered_at + timedelta(seconds=period.duration_seconds))
            if first_terminal:
                end = min(end, first_terminal)
            if end > period.entered_at:
                intervals.append((period.entered_at, end))

        st.subheader("Merged Blocked Intervals")
        merged_rows = [
            {
                "Blocked Start": start.strftime("%Y-%m-%d %H:%M"),
                "Blocked End": end.strftime("%Y-%m-%d %H:%M"),
                "Duration (h)": _duration_hours(start, end),
            }
            for start, end in _merge_intervals(intervals)
        ]
        if merged_rows:
            st.dataframe(pd.DataFrame(merged_rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No productive blocked intervals.")

    st.subheader("Computed Metrics")
    m1, m2, m3 = st.columns(3)
    m1.metric("Lead Time", f"{issue.lead_time_hours:.1f}h" if issue.lead_time_hours else "N/A")
    m2.metric("Raw Cycle Time", f"{issue.cycle_time_hours:.1f}h" if issue.cycle_time_hours else "N/A")
    m3.metric("Active Time", f"{issue.total_active_time_hours:.1f}h")

    m4, m5, m6 = st.columns(3)
    m4.metric("Buffer Time", f"{issue.buffer_time_hours:.1f}h")
    m5.metric("Blocked Time", f"{issue.blocked_time_hours:.1f}h")
    m6.metric("Terminal Blocked Time", f"{issue.terminal_blocked_time_hours:.1f}h")

    m7, m8, m9 = st.columns(3)
    m7.metric("Net Cycle Time", f"{issue.net_cycle_time_hours:.1f}h" if issue.net_cycle_time_hours is not None else "N/A")
    fe = issue.flow_efficiency_percent
    m8.metric("Gross Flow Efficiency", f"{fe:.1f}%" if fe is not None else "N/A")
    nfe = issue.net_flow_efficiency_percent
    m9.metric("Net Flow Efficiency", f"{nfe:.1f}%" if nfe is not None else "N/A")

    if issue.is_done and issue.lead_time_seconds:
        accounted = (
            issue.buffer_time_seconds
            + issue.total_active_time_seconds
            + issue.blocked_time_seconds
            + issue.waiting_time_seconds
            + issue.terminal_time_seconds
        )
        delta = abs(accounted - issue.lead_time_seconds)
        if delta > 2:
            st.warning(
                f"Buffer + Active + Blocked + Waiting + Terminal = {accounted / 3600:.1f}h vs Lead = "
                f"{issue.lead_time_hours:.1f}h (Δ {delta / 3600:.1f}h)"
            )
        else:
            st.success("Buffer + Active + Blocked + Waiting + Terminal ≈ Lead Time (within tolerance).")

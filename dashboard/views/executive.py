"""Page 1 — Executive Dashboard."""

from __future__ import annotations

import streamlit as st

from dashboard.filters import FilterState
from dashboard.loader import DashboardData


def _bottleneck_label(bottleneck) -> str:
    if bottleneck is None:
        return "N/A"
    return f"{bottleneck.status} ({bottleneck.average_hours:.1f}h)"


def _top_bottleneck(data: DashboardData):
    bn = data.analytics.bottlenecks
    candidates = [
        bn.largest_qa,
        bn.largest_review,
        bn.largest_waiting,
        bn.largest_queue,
        bn.largest_active,
    ]
    present = [b for b in candidates if b is not None]
    return max(present, key=lambda b: b.average_seconds) if present else None


def render(data: DashboardData, filters: FilterState) -> None:
    st.title("Executive Dashboard")
    if filters.is_active:
        st.info("KPIs reflect full analytics.json dataset. Filters apply to detail pages only.")

    summary = data.analytics.summary
    project = data.metrics.project
    aging = data.analytics.aging
    bugs = data.metrics.bug_analytics
    top = _top_bottleneck(data)

    lead_h = project.median_lead_time_seconds / 3600 if project.median_lead_time_seconds else None
    buffer_h = project.median_buffer_time_seconds / 3600 if project.median_buffer_time_seconds else None
    blocked_h = project.median_blocked_time_seconds / 3600 if project.median_blocked_time_seconds else None
    bug_rate = bugs.bug_rate_percent or project.bug_rate_percent
    fe = summary.average_flow_efficiency_percent

    row1 = st.columns(5)
    row1[0].metric("Lead Time (median)", f"{lead_h:.1f}h" if lead_h else "N/A")
    row1[1].metric("Buffer Time (median)", f"{buffer_h:.1f}h" if buffer_h else "N/A")
    row1[2].metric("Throughput", summary.total_throughput)
    row1[3].metric("Bug Rate", f"{bug_rate:.1f}%" if bug_rate is not None else "N/A")
    row1[4].metric("Flow Efficiency", f"{fe:.1f}%" if fe is not None else "N/A")

    row2 = st.columns(5)
    row2[0].metric("Reopen %", f"{summary.reopen_percent:.1f}%")
    avg_aging = aging.average_seconds / 3600 if aging.average_seconds else None
    row2[1].metric("Average Aging", f"{avg_aging:.1f}h" if avg_aging else "N/A")
    p90_aging = aging.p90_seconds / 3600 if aging.p90_seconds else None
    row2[2].metric("P90 Aging", f"{p90_aging:.1f}h" if p90_aging else "N/A")
    row2[3].metric("Blocked Time (median)", f"{blocked_h:.1f}h" if blocked_h else "N/A")
    row2[4].metric("Blocked Issue %", f"{project.blocked_issue_percent:.1f}%" if project.blocked_issue_percent is not None else "N/A")

    row3 = st.columns(5)
    row3[0].metric("Total Issues", summary.total_issues)
    row3[1].metric("Completed", summary.completed_issues)
    row3[2].metric("Open", summary.open_issues)
    cycle_h = project.median_cycle_time_seconds / 3600 if project.median_cycle_time_seconds else None
    row3[3].metric("Cycle Time (median)", f"{cycle_h:.1f}h" if cycle_h else "N/A")
    row3[4].metric("Largest Bottleneck", _bottleneck_label(top))

    st.caption(
        f"Project {data.project_key} · Analytics generated {data.analytics.generated_at:%Y-%m-%d %H:%M UTC}"
    )

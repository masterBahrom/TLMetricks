"""Deterministic management insights for the dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dashboard.loader import DashboardData

from jira_analytics.reports.insights import generate_insights as _base_insights


FLOW_EFFICIENCY_TARGET = 50.0


def generate_insights(data: DashboardData) -> list[str]:
    """Extend report insights with dashboard-specific deterministic rules."""
    insights = list(_base_insights(data.metrics, data.analytics, data.workflow))

    summary = data.analytics.summary
    project = data.metrics.project
    queues = {entry.category: entry for entry in data.analytics.queues.categories}

    if summary.average_flow_efficiency_percent is not None:
        if summary.average_flow_efficiency_percent < FLOW_EFFICIENCY_TARGET:
            insights.append(
                f"Flow Efficiency ({summary.average_flow_efficiency_percent:.0f}%) "
                f"is below the {FLOW_EFFICIENCY_TARGET:.0f}% target."
            )

    waiting = queues.get("waiting")
    active = queues.get("active")
    if waiting and active and waiting.total_seconds > active.total_seconds:
        insights.append("Waiting time exceeds Active development time across the workflow.")

    if summary.reopen_percent >= 10:
        insights.append("Too many reopened issues — review quality gates and definition of done.")

    weekly = data.analytics.trend.throughput.weekly
    if len(weekly) >= 2:
        recent = weekly[-1].count
        prior = weekly[-2].count
        if prior > 0 and recent < prior * 0.8:
            drop = (1 - recent / prior) * 100
            insights.append(f"Throughput decreased by {drop:.0f}% in the most recent week.")

    if data.analytics.aging.top_oldest:
        oldest = max(data.analytics.aging.top_oldest, key=lambda entry: entry.aging_days)
        insights.append(
            f"Oldest open issue: {oldest.issue_key} ({oldest.aging_days:.0f} days in {oldest.current_status})."
        )

    if data.analytics.distributions.status.by_status:
        worst = max(data.analytics.distributions.status.by_status, key=lambda entry: entry.average_hours)
        insights.append(
            f"Most time-consuming status: {worst.status} "
            f"({worst.average_hours:.1f}h average across {worst.issue_count} issues)."
        )

    bn = data.analytics.bottlenecks
    if bn.largest_qa and bn.largest_review:
        if bn.largest_qa.average_seconds >= bn.largest_review.average_seconds:
            insights.append(f"QA ({bn.largest_qa.status}) is the primary delivery bottleneck.")

    if project.median_lead_time_seconds and project.average_lead_time_seconds:
        if project.average_lead_time_seconds > project.median_lead_time_seconds * 1.15:
            increase = (
                (project.average_lead_time_seconds - project.median_lead_time_seconds)
                / project.median_lead_time_seconds
            ) * 100
            insights.append(f"Average Lead Time is {increase:.0f}% above median — long-tail issues present.")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in insights:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique

"""Deterministic management insights from analytics data."""

from __future__ import annotations

from jira_analytics.analytics.models import AnalyticsDocument
from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import MetricsDocument
from jira_analytics.utils.stats import percentile


def generate_insights(
    metrics: MetricsDocument,
    analytics: AnalyticsDocument,
    workflow: WorkflowConfig,
) -> list[str]:
    """Produce actionable observations without AI — rule-based only."""
    insights: list[str] = []
    project = metrics.project
    summary = analytics.summary
    queues = {entry.category: entry for entry in analytics.queues.categories}

    # Flow efficiency
    if summary.average_flow_efficiency_percent is not None:
        fe = summary.average_flow_efficiency_percent
        if fe < 40:
            insights.append(f"Average Flow Efficiency is only {fe:.0f}% — most lead time is non-value-add waiting.")
        elif fe < 60:
            insights.append(f"Average Flow Efficiency is {fe:.0f}% — significant room to reduce waiting time.")
        else:
            insights.append(f"Average Flow Efficiency is {fe:.0f}%.")

    # Waiting share of lead time
    if project.average_lead_time_seconds and project.average_waiting_time_seconds:
        wait_pct = (project.average_waiting_time_seconds / project.average_lead_time_seconds) * 100
        if wait_pct >= 30:
            insights.append(f"{wait_pct:.0f}% of total Lead Time is spent waiting.")

    # Queue vs review ratio
    review = queues.get("review")
    waiting = queues.get("waiting")
    queue = queues.get("queue")
    if review and waiting and waiting.total_seconds > 0:
        ratio = review.total_seconds / waiting.total_seconds
        if ratio < 0.5:
            insights.append(
                f"Team spends {1/ratio:.1f}x more time waiting than reviewing."
                if ratio > 0
                else "Waiting time exceeds review time significantly."
            )
    if queue and review and review.total_seconds > 0:
        ratio = queue.total_seconds / review.total_seconds
        if ratio > 2:
            insights.append(f"Queue time is {ratio:.1f}x review time — backlog may be building.")

    # Bottlenecks
    bn = analytics.bottlenecks
    candidates = [
        (bn.largest_qa, "QA"),
        (bn.largest_review, "Code Review"),
        (bn.largest_waiting, "Waiting"),
        (bn.largest_queue, "Queue"),
        (bn.largest_active, "Active work"),
    ]
    bottlenecks = [(b, label) for b, label in candidates if b is not None]
    if bottlenecks:
        top = max(bottlenecks, key=lambda item: item[0].average_seconds)
        insights.append(
            f"{top[1]} ({top[0].status}) is the largest bottleneck "
            f"at {top[0].average_hours:.1f} hours average."
        )

    # Review % of cycle
    if project.average_cycle_time_seconds and review:
        review_pct = (review.total_seconds / max(project.average_cycle_time_seconds, 1)) * 100
        if review_pct >= 20:
            insights.append(f"Code Review consumes {review_pct:.0f}% of average Cycle Time.")

    # Reopens
    if summary.reopen_percent > 0:
        insights.append(
            f"{metrics.project.reopened_count} issue(s) were reopened "
            f"({summary.reopen_percent:.0f}% of all issues)."
        )
    if project.average_reopens > 0.5:
        insights.append(f"Average reopen count is {project.average_reopens:.1f} per issue.")

    # Aging
    aging = analytics.aging
    if aging.open_issue_count > 0:
        old_threshold_days = 30
        old_count = sum(1 for entry in aging.top_oldest if entry.aging_days >= old_threshold_days)
        if old_count:
            insights.append(f"{old_count} open issue(s) are older than {old_threshold_days} days.")
        if aging.average_seconds:
            insights.append(f"Average aging for open issues is {aging.average_seconds / 86400:.1f} days.")
    elif metrics.project.open_count == 0:
        insights.append("No open issues — aging backlog is clear.")

    # Throughput stability
    weekly = analytics.trend.throughput.weekly
    if len(weekly) >= 3:
        counts = [bucket.count for bucket in weekly[-8:]]
        if counts:
            avg = sum(counts) / len(counts)
            spread = max(counts) - min(counts)
            if avg > 0 and spread / avg <= 0.3:
                insights.append(f"Throughput is stable across the last {len(counts)} weeks.")
            elif spread > avg:
                insights.append(f"Throughput varies significantly week-to-week (range {min(counts)}–{max(counts)}).")

    # Lead vs cycle gap
    if project.median_lead_time_seconds and project.median_cycle_time_seconds:
        gap_pct = (
            (project.median_lead_time_seconds - project.median_cycle_time_seconds)
            / project.median_lead_time_seconds
        ) * 100
        if gap_pct > 25:
            insights.append(
                f"Median Lead Time exceeds Cycle Time by {gap_pct:.0f}% — investigate queue and handoff delays."
            )

    # P90 lead time warning
    lead_times = [
        issue.lead_time_seconds
        for issue in metrics.issues
        if issue.lead_time_seconds is not None
    ]
    if lead_times and project.median_lead_time_seconds:
        p90 = percentile(lead_times, 90)
        if p90 and p90 > project.median_lead_time_seconds * 1.5:
            insights.append(
                f"P90 Lead Time ({p90 / 3600:.1f}h) is significantly above median "
                f"({project.median_lead_time_seconds / 3600:.1f}h) — outliers present."
            )

    # Cancelled terminal status
    if workflow.cancelled_statuses:
        cancelled_set = {s.strip().lower() for s in workflow.cancelled_statuses}
        cancelled = [
            issue
            for issue in metrics.issues
            if issue.current_status and issue.current_status.strip().lower() in cancelled_set
        ]
        if cancelled:
            insights.append(f"{len(cancelled)} issue(s) completed as Cancelled.")

    if not insights:
        insights.append("No significant anomalies detected in the current dataset.")

    return insights

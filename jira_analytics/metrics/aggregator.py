"""Project-level metric aggregation from issue metrics."""

from __future__ import annotations

import logging

from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.metrics.bug_rate import compute_bug_analytics, mark_bug_flags
from jira_analytics.models.metrics import (
    BugAnalytics,
    IssueMetrics,
    MetricsDocument,
    ProjectMetrics,
    StatusAverage,
)
from jira_analytics.utils.stats import percentile, safe_mean, seconds_to_days, seconds_to_hours

logger = logging.getLogger(__name__)


class ProjectAggregator:
    """Aggregate issue-level metrics into project-level statistics."""

    def aggregate(
        self,
        project_key: str,
        issues: list[IssueMetrics],
        *,
        workflow: WorkflowConfig | None = None,
    ) -> tuple[ProjectMetrics, BugAnalytics]:
        workflow = workflow or WorkflowConfig()
        issues = mark_bug_flags(issues, workflow)
        bug_analytics = compute_bug_analytics(issues, workflow)

        done_issues = [issue for issue in issues if issue.is_done]
        open_issues = [issue for issue in issues if not issue.is_done]
        reopened_issues = [issue for issue in issues if issue.is_reopened]

        lead_times = [issue.lead_time_seconds for issue in done_issues if issue.lead_time_seconds is not None]
        cycle_times = [issue.cycle_time_seconds for issue in done_issues if issue.cycle_time_seconds is not None]
        net_cycle_times = [
            issue.net_cycle_time_seconds
            for issue in done_issues
            if issue.net_cycle_time_seconds is not None
        ]
        ttfg_values = [
            issue.time_to_first_progress_seconds
            for issue in issues
            if issue.time_to_first_progress_seconds is not None
        ]
        active_times = [issue.total_active_time_seconds for issue in issues]
        buffer_times = [issue.buffer_time_seconds for issue in issues]
        blocked_times = [issue.blocked_time_seconds for issue in issues]
        blocked_issues = [issue for issue in issues if issue.blocked_time_seconds > 0]
        net_flow_values = [
            issue.net_flow_efficiency_percent
            for issue in done_issues
            if issue.net_flow_efficiency_percent is not None
        ]
        waiting_times = [issue.waiting_time_seconds for issue in issues]
        reopen_counts = [float(issue.reopen_count) for issue in issues]

        status_averages = self._aggregate_time_by_status(issues)

        metrics = ProjectMetrics(
            project_key=project_key,
            total_issues=len(issues),
            done_count=len(done_issues),
            open_count=len(open_issues),
            reopened_count=len(reopened_issues),
            throughput=len(done_issues),
            average_lead_time_seconds=safe_mean(lead_times),
            median_lead_time_seconds=percentile(lead_times, 50),
            p90_lead_time_seconds=percentile(lead_times, 90),
            average_cycle_time_seconds=safe_mean(cycle_times),
            median_cycle_time_seconds=percentile(cycle_times, 50),
            p90_cycle_time_seconds=percentile(cycle_times, 90),
            average_net_cycle_time_seconds=safe_mean(net_cycle_times),
            median_net_cycle_time_seconds=percentile(net_cycle_times, 50),
            average_time_to_first_progress_seconds=safe_mean(ttfg_values),
            average_active_time_seconds=safe_mean(active_times),
            average_buffer_time_seconds=safe_mean(buffer_times),
            median_buffer_time_seconds=percentile(buffer_times, 50),
            p75_buffer_time_seconds=percentile(buffer_times, 75),
            p90_buffer_time_seconds=percentile(buffer_times, 90),
            p95_buffer_time_seconds=percentile(buffer_times, 95),
            total_buffer_time_seconds=sum(buffer_times) if buffer_times else None,
            average_blocked_time_seconds=safe_mean(blocked_times),
            median_blocked_time_seconds=percentile(blocked_times, 50),
            p75_blocked_time_seconds=percentile(blocked_times, 75),
            p90_blocked_time_seconds=percentile(blocked_times, 90),
            p95_blocked_time_seconds=percentile(blocked_times, 95),
            blocked_issue_count=len(blocked_issues),
            blocked_issue_percent=round(len(blocked_issues) / len(issues) * 100, 4) if issues else None,
            average_net_flow_efficiency_percent=round(safe_mean(net_flow_values), 4)
            if net_flow_values
            else None,
            average_waiting_time_seconds=safe_mean(waiting_times),
            average_reopens=safe_mean(reopen_counts) or 0.0,
            completed_bugs=bug_analytics.completed_bugs,
            completed_hotfix=bug_analytics.completed_hotfix,
            total_bugs=bug_analytics.total_bugs,
            bug_rate_percent=bug_analytics.bug_rate_percent,
            average_time_by_status=status_averages,
        )

        logger.info(
            "Aggregated project metrics: %d issues (%d done, %d open, %d bugs)",
            metrics.total_issues,
            metrics.done_count,
            metrics.open_count,
            metrics.total_bugs,
        )
        return metrics, bug_analytics

    def build_document(
        self,
        project_key: str,
        issues: list[IssueMetrics],
        *,
        workflow: WorkflowConfig | None = None,
        source_timelines_at=None,
        source_issues_at=None,
    ) -> MetricsDocument:
        project, bug_analytics = self.aggregate(project_key, issues, workflow=workflow)
        flagged_issues = mark_bug_flags(issues, workflow or WorkflowConfig())
        return MetricsDocument.from_parts(
            project,
            flagged_issues,
            source_timelines_at=source_timelines_at,
            source_issues_at=source_issues_at,
            bug_analytics=bug_analytics,
        )

    @staticmethod
    def _aggregate_time_by_status(issues: list[IssueMetrics]) -> list[StatusAverage]:
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}

        for issue in issues:
            for entry in issue.time_in_status:
                totals[entry.status] = totals.get(entry.status, 0.0) + entry.duration_seconds
                counts[entry.status] = counts.get(entry.status, 0) + 1

        return [
            StatusAverage(
                status=status,
                average_seconds=avg_seconds,
                average_hours=seconds_to_hours(avg_seconds),
                average_days=seconds_to_days(avg_seconds),
                issue_count=counts[status],
            )
            for status, avg_seconds in sorted(
                ((s, totals[s] / counts[s]) for s in totals),
                key=lambda item: item[0],
            )
        ]

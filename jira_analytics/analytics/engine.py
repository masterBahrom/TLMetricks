"""Analytics Engine — orchestrates advanced engineering analytics."""

from __future__ import annotations

import logging
from datetime import datetime

from jira_analytics.analytics.aging import compute_aging
from jira_analytics.analytics.bottlenecks import compute_bottlenecks
from jira_analytics.analytics.flow import compute_flow_efficiency
from jira_analytics.analytics.models import (
    AnalyticsDocument,
    AnalyticsSummary,
    DistributionAnalytics,
    TrendAnalytics,
)
from jira_analytics.analytics.queues import compute_queue_analysis
from jira_analytics.analytics.reopen import compute_reopen_analytics
from jira_analytics.analytics.status_distribution import compute_status_distribution
from jira_analytics.analytics.throughput import compute_throughput_distribution, compute_throughput_timeline
from jira_analytics.analytics.wip import compute_wip_timeline
from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import MetricsDocument
from jira_analytics.models.timeline import TimelinesDocument
from jira_analytics.utils.datetime_utils import utc_now
from jira_analytics.utils.stats import seconds_to_hours

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    Build advanced analytics from metrics, timelines, and workflow configuration.

    Uses only Phase 3/2 cache outputs — no Jira API calls.
    """

    def __init__(
        self,
        workflow: WorkflowConfig,
        reference_time: datetime | None = None,
    ) -> None:
        self._workflow = workflow
        self._reference = reference_time or utc_now()

    def run(
        self,
        metrics: MetricsDocument,
        timelines: TimelinesDocument,
    ) -> AnalyticsDocument:
        """Compute the full analytics document."""
        issues = metrics.issues
        timeline_map = timelines.timelines

        throughput_timeline = compute_throughput_timeline(issues)
        throughput_distribution = compute_throughput_distribution(issues)
        wip_timeline = compute_wip_timeline(timeline_map, issues, self._workflow, self._reference)
        aging = compute_aging(issues, timeline_map, self._reference)
        flow = compute_flow_efficiency(issues)
        queues = compute_queue_analysis(issues, self._workflow)
        status_dist = compute_status_distribution(issues, self._workflow)
        bottlenecks = compute_bottlenecks(issues, self._workflow)
        reopen = compute_reopen_analytics(issues)

        summary = AnalyticsSummary(
            project_key=metrics.project.project_key,
            total_issues=metrics.project.total_issues,
            completed_issues=metrics.project.done_count,
            open_issues=metrics.project.open_count,
            total_throughput=metrics.project.throughput,
            average_flow_efficiency_percent=flow.average_efficiency_percent,
            reopen_percent=reopen.reopen_percent,
            average_aging_hours=seconds_to_hours(aging.average_seconds) if aging.average_seconds else None,
        )

        document = AnalyticsDocument(
            source_metrics_at=metrics.generated_at,
            source_timelines_at=timelines.generated_at,
            project_key=metrics.project.project_key,
            summary=summary,
            trend=TrendAnalytics(throughput=throughput_timeline, wip=wip_timeline),
            distributions=DistributionAnalytics(
                throughput=throughput_distribution,
                status=status_dist,
            ),
            flow=flow,
            queues=queues,
            bottlenecks=bottlenecks,
            aging=aging,
            throughput=throughput_timeline,
        )

        logger.info(
            "Analytics computed for %s: %d issues, throughput=%d",
            document.project_key,
            document.summary.total_issues,
            document.summary.total_throughput,
        )
        return document

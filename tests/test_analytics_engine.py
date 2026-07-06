"""Integration-style tests for Analytics Engine."""

from __future__ import annotations

from datetime import datetime, timezone

from jira_analytics.analytics import AnalyticsEngine, AnalyticsValidator
from jira_analytics.metrics.aggregator import ProjectAggregator
from jira_analytics.metrics.calculator import MetricCalculator
from jira_analytics.models.metrics import MetricsDocument
from jira_analytics.models.timeline import TimelinesDocument
from jira_analytics.parser.timeline_builder import TimelineBuilder

from tests.conftest import REFERENCE, history, make_issue, make_registry, make_workflow

UTC = timezone.utc


def _build_pipeline(issue: dict, histories: list) -> tuple[MetricsDocument, TimelinesDocument]:
    workflow = make_workflow()
    timeline = TimelineBuilder(make_registry(), reference_time=REFERENCE).build_issue_timeline(issue, histories)
    metrics = MetricCalculator(workflow).calculate(timeline)
    project, _ = ProjectAggregator().aggregate("TL", [metrics], workflow=make_workflow())
    metrics_doc = MetricsDocument.from_parts(project, [metrics], source_timelines_at=REFERENCE)
    timelines_doc = TimelinesDocument(
        generated_at=REFERENCE,
        issue_count=1,
        timelines={timeline.issue_key: timeline},
    )
    return metrics_doc, timelines_doc


class TestFlowEfficiency:
    def test_flow_efficiency_from_active_and_lead(self) -> None:
        issue = make_issue(
            "TL-1",
            created="2025-01-01T09:00:00.000+0000",
            status_id="9",
            status_name="Done",
            resolution="2025-01-05T17:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "4", "Review"),
            history("3", "2025-01-03T10:00:00.000+0000", "4", "Review", "6", "QA IN PROGRESS"),
            history("4", "2025-01-04T10:00:00.000+0000", "6", "QA IN PROGRESS", "9", "Done"),
        ]
        metrics_doc, timelines_doc = _build_pipeline(issue, histories)
        analytics = AnalyticsEngine(make_workflow(), reference_time=REFERENCE).run(metrics_doc, timelines_doc)

        assert analytics.flow.average_efficiency_percent is not None
        assert analytics.flow.average_efficiency_percent <= 100.0
        expected = (72 / 104) * 100
        assert abs(analytics.flow.average_efficiency_percent - expected) < 1.0


class TestTerminalPipeline:
    def test_done_to_post_deployment_not_reopen(self) -> None:
        issue = make_issue(
            "TL-2",
            created="2025-01-01T09:00:00.000+0000",
            status_id="8",
            status_name="Post Deployment",
            resolution="2025-01-06T10:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
            history("3", "2025-01-03T10:00:00.000+0000", "9", "Done", "8", "Post Deployment"),
        ]
        metrics_doc, timelines_doc = _build_pipeline(issue, histories)
        analytics = AnalyticsEngine(make_workflow(), reference_time=REFERENCE).run(metrics_doc, timelines_doc)

        assert analytics.summary.reopen_percent == 0.0
        assert analytics.summary.total_throughput == 1


class TestCancelled:
    def test_cancelled_counts_as_completed(self) -> None:
        issue = make_issue(
            "TL-3",
            created="2025-01-01T09:00:00.000+0000",
            status_id="10",
            status_name="Cancelled",
            resolution="2025-01-02T10:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "10", "Cancelled"),
        ]
        metrics_doc, timelines_doc = _build_pipeline(issue, histories)
        analytics = AnalyticsEngine(make_workflow(), reference_time=REFERENCE).run(metrics_doc, timelines_doc)

        assert analytics.summary.completed_issues == 1
        assert analytics.summary.total_throughput == 1


class TestReopened:
    def test_reopen_analytics(self) -> None:
        issue = make_issue("TL-4", created="2025-01-01T09:00:00.000+0000", status_id="9", status_name="Done")
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "9", "Done"),
            history("2", "2025-01-03T10:00:00.000+0000", "9", "Done", "3", "In Progress"),
            history("3", "2025-01-04T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
        ]
        metrics_doc, timelines_doc = _build_pipeline(issue, histories)
        analytics = AnalyticsEngine(make_workflow(), reference_time=REFERENCE).run(metrics_doc, timelines_doc)

        assert analytics.summary.reopen_percent == 100.0
        assert len(analytics.flow.per_issue) == 1


class TestOpenIssueAging:
    def test_aging_only_for_open(self) -> None:
        issue = make_issue("TL-5", created="2025-01-01T09:00:00.000+0000", status_id="3", status_name="In Progress")
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
        ]
        metrics_doc, timelines_doc = _build_pipeline(issue, histories)
        analytics = AnalyticsEngine(make_workflow(), reference_time=REFERENCE).run(metrics_doc, timelines_doc)

        assert analytics.aging.open_issue_count == 1
        assert analytics.aging.top_oldest[0].issue_key == "TL-5"
        assert analytics.summary.completed_issues == 0


class TestWaitingStatuses:
    def test_queue_analysis_includes_waiting(self) -> None:
        workflow = make_workflow()
        issue = make_issue("TL-6", created="2025-01-01T09:00:00.000+0000", status_id="3", status_name="In Progress")
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
        ]
        timeline = TimelineBuilder(make_registry(), reference_time=REFERENCE).build_issue_timeline(issue, histories)
        metrics = MetricCalculator(workflow).calculate(timeline)
        project, _ = ProjectAggregator().aggregate("TL", [metrics], workflow=make_workflow())
        metrics_doc = MetricsDocument.from_parts(project, [metrics])
        timelines_doc = TimelinesDocument(timelines={timeline.issue_key: timeline}, issue_count=1)

        analytics = AnalyticsEngine(workflow, reference_time=REFERENCE).run(metrics_doc, timelines_doc)
        categories = {entry.category: entry for entry in analytics.queues.categories}

        assert "queue" in categories
        assert categories["queue"].total_seconds > 0


class TestBottlenecks:
    def test_detects_review_bottleneck(self) -> None:
        issue = make_issue(
            "TL-7",
            created="2025-01-01T09:00:00.000+0000",
            status_id="9",
            status_name="Done",
            resolution="2025-01-05T17:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "4", "Review"),
            history("3", "2025-01-04T10:00:00.000+0000", "4", "Review", "9", "Done"),
        ]
        metrics_doc, timelines_doc = _build_pipeline(issue, histories)
        analytics = AnalyticsEngine(make_workflow(), reference_time=REFERENCE).run(metrics_doc, timelines_doc)

        assert analytics.bottlenecks.largest_review is not None
        assert analytics.bottlenecks.largest_review.status == "Review"


class TestThroughputTimeline:
    def test_daily_throughput(self) -> None:
        issue = make_issue(
            "TL-8",
            created="2025-01-01T09:00:00.000+0000",
            status_id="9",
            status_name="Done",
            resolution="2025-01-05T17:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-04T10:00:00.000+0000", "6", "QA IN PROGRESS", "9", "Done"),
        ]
        metrics_doc, timelines_doc = _build_pipeline(issue, histories)
        analytics = AnalyticsEngine(make_workflow(), reference_time=REFERENCE).run(metrics_doc, timelines_doc)

        assert sum(bucket.count for bucket in analytics.throughput.daily) == 1
        report = AnalyticsValidator().validate(analytics, metrics_doc)
        assert report.is_valid


class TestWorkflowConfigVariations:
    def test_custom_terminal_statuses(self) -> None:
        from jira_analytics.config.workflow import WorkflowConfig

        custom = WorkflowConfig(
            terminal_statuses=["Released", "Production"],
            cancelled_statuses=["Cancelled"],
            active_statuses=["Development"],
            review_statuses=[],
            qa_statuses=[],
            waiting_statuses=["Backlog"],
        )
        issue = make_issue(
            "TL-9",
            created="2025-01-01T09:00:00.000+0000",
            status_id="8",
            status_name="Released",
            resolution="2025-01-03T10:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "3", "Development"),
            history("2", "2025-01-03T10:00:00.000+0000", "3", "Development", "8", "Released"),
        ]
        timeline = TimelineBuilder(make_registry(), reference_time=REFERENCE).build_issue_timeline(issue, histories)
        metrics = MetricCalculator(custom).calculate(timeline)
        project, _ = ProjectAggregator().aggregate("TL", [metrics], workflow=make_workflow())
        metrics_doc = MetricsDocument.from_parts(project, [metrics])
        timelines_doc = TimelinesDocument(timelines={timeline.issue_key: timeline}, issue_count=1)

        analytics = AnalyticsEngine(custom, reference_time=REFERENCE).run(metrics_doc, timelines_doc)
        assert analytics.summary.total_throughput == 1

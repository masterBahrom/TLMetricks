"""Unit tests for metrics validation."""

from __future__ import annotations

from datetime import datetime, timezone

from jira_analytics.metrics.calculator import MetricCalculator
from jira_analytics.metrics.aggregator import ProjectAggregator
from jira_analytics.models.metrics import IssueMetrics, MetricsDocument, TimeInStatus
from jira_analytics.parser.timeline_builder import TimelineBuilder
from jira_analytics.validators.metrics_validator import MetricsValidator

from tests.conftest import REFERENCE, history, make_issue, make_registry, make_workflow

UTC = timezone.utc


def _valid_done_metrics() -> IssueMetrics:
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
    timeline = TimelineBuilder(make_registry(), reference_time=REFERENCE).build_issue_timeline(issue, histories)
    return MetricCalculator(make_workflow()).calculate(timeline)


class TestMetricsValidator:
    def test_valid_metrics_pass(self) -> None:
        metrics = _valid_done_metrics()
        project, _ = ProjectAggregator().aggregate("TL", [metrics], workflow=make_workflow())
        doc = MetricsDocument.from_parts(project, [metrics])
        report = MetricsValidator().validate_document(doc)
        assert report.is_valid

    def test_cycle_exceeds_lead_fails(self) -> None:
        metrics = IssueMetrics(
            issue_key="TL-X",
            issue_id="1",
            created_date=datetime(2025, 1, 1, tzinfo=UTC),
            is_done=True,
            done_date=datetime(2025, 1, 5, tzinfo=UTC),
            lead_time_seconds=100.0,
            cycle_time_seconds=200.0,
            total_active_time_seconds=200.0,
            waiting_time_seconds=0.0,
        )
        project, _ = ProjectAggregator().aggregate("TL", [metrics], workflow=make_workflow())
        doc = MetricsDocument.from_parts(project, [metrics])
        report = MetricsValidator().validate_document(doc)
        assert not report.is_valid
        assert any(i.code == "CYCLE_EXCEEDS_LEAD" for i in report.issues)

    def test_open_with_resolution_fails(self) -> None:
        metrics = IssueMetrics(
            issue_key="TL-Y",
            issue_id="2",
            created_date=datetime(2025, 1, 1, tzinfo=UTC),
            is_done=False,
            resolution_time_seconds=100.0,
        )
        project, _ = ProjectAggregator().aggregate("TL", [metrics], workflow=make_workflow())
        doc = MetricsDocument.from_parts(project, [metrics])
        report = MetricsValidator().validate_document(doc)
        assert not report.is_valid
        assert any(i.code == "OPEN_HAS_RESOLUTION" for i in report.issues)

    def test_negative_value_fails(self) -> None:
        metrics = IssueMetrics(
            issue_key="TL-Z",
            issue_id="3",
            created_date=datetime(2025, 1, 1, tzinfo=UTC),
            is_done=True,
            done_date=datetime(2025, 1, 2, tzinfo=UTC),
            lead_time_seconds=-1.0,
            total_active_time_seconds=0.0,
            waiting_time_seconds=0.0,
        )
        project, _ = ProjectAggregator().aggregate("TL", [metrics], workflow=make_workflow())
        doc = MetricsDocument.from_parts(project, [metrics])
        report = MetricsValidator().validate_document(doc)
        assert not report.is_valid

    def test_nan_fails(self) -> None:
        metrics = IssueMetrics(
            issue_key="TL-N",
            issue_id="4",
            created_date=datetime(2025, 1, 1, tzinfo=UTC),
            is_done=True,
            done_date=datetime(2025, 1, 2, tzinfo=UTC),
            lead_time_seconds=float("nan"),
            total_active_time_seconds=0.0,
            waiting_time_seconds=0.0,
        )
        project, _ = ProjectAggregator().aggregate("TL", [metrics], workflow=make_workflow())
        doc = MetricsDocument.from_parts(project, [metrics])
        report = MetricsValidator().validate_document(doc)
        assert not report.is_valid
        assert any(i.code == "NON_FINITE" for i in report.issues)

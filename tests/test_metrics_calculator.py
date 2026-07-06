"""Unit tests for MetricCalculator."""

from __future__ import annotations

from datetime import datetime, timezone

from jira_analytics.metrics.calculator import MetricCalculator
from jira_analytics.models.timeline import IssueTimeline, StatusPeriod

from tests.conftest import REFERENCE, history, make_issue, make_registry, make_workflow
from jira_analytics.parser.timeline_builder import TimelineBuilder

UTC = timezone.utc


def _calc() -> MetricCalculator:
    return MetricCalculator(make_workflow())


def _build(issue: dict, histories: list) -> IssueTimeline:
    return TimelineBuilder(make_registry(), reference_time=REFERENCE).build_issue_timeline(issue, histories)


class TestNormalWorkflow:
    def test_tl123_metrics(self) -> None:
        issue = make_issue(
            "TL-123",
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
        timeline = _build(issue, histories)
        metrics = _calc().calculate(timeline)

        assert metrics.is_done is True
        assert metrics.lead_time_seconds == 104 * 3600
        assert metrics.cycle_time_seconds == 72 * 3600
        assert metrics.total_active_time_seconds == 72 * 3600
        assert metrics.buffer_time_seconds == 3600
        assert metrics.buffer_time_hours == 1.0
        assert metrics.terminal_time_seconds == 31 * 3600
        assert metrics.time_to_first_progress_seconds == 3600
        assert metrics.flow_efficiency_percent is not None
        assert metrics.flow_efficiency_percent <= 100.0
        assert metrics.status_count == 5
        assert metrics.reopen_count == 0
        assert metrics.lead_time_seconds >= metrics.cycle_time_seconds  # type: ignore[operator]


class TestNoChangelog:
    def test_open_single_status(self) -> None:
        issue = make_issue("TL-10", created="2025-01-01T09:00:00.000+0000", status_id="3", status_name="In Progress")
        timeline = _build(issue, [])
        metrics = _calc().calculate(timeline)

        assert metrics.is_done is False
        assert metrics.lead_time_seconds is None
        assert metrics.cycle_time_seconds is None
        assert metrics.resolution_time_seconds is None
        assert metrics.total_active_time_seconds > 0
        assert metrics.status_count == 1


class TestReopen:
    def test_reopen_count(self) -> None:
        issue = make_issue("TL-11", created="2025-01-01T09:00:00.000+0000", status_id="9", status_name="Done")
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "9", "Done"),
            history("2", "2025-01-03T10:00:00.000+0000", "9", "Done", "3", "In Progress"),
            history("3", "2025-01-04T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
        ]
        metrics = _calc().calculate(_build(issue, histories))

        assert metrics.is_reopened is True
        assert metrics.reopen_count == 1
        assert metrics.is_done is True


class TestWithoutDone:
    def test_open_issue(self) -> None:
        issue = make_issue("TL-12", created="2025-01-01T09:00:00.000+0000", status_id="3", status_name="In Progress")
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
        ]
        metrics = _calc().calculate(_build(issue, histories))

        assert metrics.is_done is False
        assert metrics.lead_time_seconds is None
        assert metrics.done_date is None


class TestDoneImmediately:
    def test_todo_to_done(self) -> None:
        issue = make_issue(
            "TL-13",
            created="2025-01-01T09:00:00.000+0000",
            status_id="9",
            status_name="Done",
            resolution="2025-01-02T10:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "9", "Done"),
        ]
        metrics = _calc().calculate(_build(issue, histories))

        assert metrics.is_done is True
        assert metrics.cycle_time_seconds is None  # never entered active status
        assert metrics.lead_time_seconds is not None


class TestMultipleActiveStatuses:
    def test_active_time_sums_indeterminate(self) -> None:
        issue = make_issue("TL-14", created="2025-01-01T09:00:00.000+0000", status_id="9", status_name="Done",
                           resolution="2025-01-05T17:00:00.000+0000")
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "4", "Review"),
            history("3", "2025-01-03T10:00:00.000+0000", "4", "Review", "6", "QA IN PROGRESS"),
            history("4", "2025-01-04T10:00:00.000+0000", "6", "QA IN PROGRESS", "9", "Done"),
        ]
        metrics = _calc().calculate(_build(issue, histories))

        assert metrics.total_active_time_seconds == 72 * 3600
        status_names = {entry.status for entry in metrics.time_in_status}
        assert "In Progress" in status_names
        assert "Review" in status_names
        assert "QA IN PROGRESS" in status_names


class TestMultipleDone:
    def test_two_done_periods(self) -> None:
        issue = make_issue("TL-15", created="2025-01-01T09:00:00.000+0000", status_id="9", status_name="Done")
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "9", "Done"),
            history("2", "2025-01-04T10:00:00.000+0000", "9", "Done", "3", "In Progress"),
            history("3", "2025-01-05T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
        ]
        metrics = _calc().calculate(_build(issue, histories))
        assert metrics.reopen_count == 1


class TestZeroDurations:
    def test_instant_transition(self) -> None:
        issue = make_issue("TL-16", created="2025-01-01T09:00:00.000+0000", status_id="9", status_name="Done")
        histories = [
            history("1", "2025-01-01T09:00:00.000+0000", "2", "To Do", "9", "Done"),
        ]
        timeline = _build(issue, histories)
        metrics = _calc().calculate(timeline)

        assert metrics.is_done is True
        assert metrics.lead_time_seconds is not None
        assert metrics.lead_time_seconds >= 0


class TestTimezone:
    def test_positive_offset_parsed(self) -> None:
        issue = make_issue(
            "TL-17",
            created="2025-01-01T09:00:00.000+0530",
            status_id="9",
            status_name="Done",
            resolution="2025-01-02T09:00:00.000+0530",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0530", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T08:00:00.000+0530", "3", "In Progress", "9", "Done"),
        ]
        metrics = _calc().calculate(_build(issue, histories))
        assert metrics.is_done is True
        assert metrics.lead_time_seconds is not None


class TestTerminalPipeline:
    """Done → Post Deployment → Released must NOT count as reopen."""

    def test_done_to_post_deployment_not_reopen(self) -> None:
        issue = make_issue(
            "TL-20",
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
        metrics = _calc().calculate(_build(issue, histories))

        assert metrics.is_done is True
        assert metrics.reopen_count == 0
        assert metrics.is_reopened is False

    def test_done_to_post_deployment_twice_not_reopen(self) -> None:
        issue = make_issue(
            "TL-21",
            created="2025-01-01T09:00:00.000+0000",
            status_id="8",
            status_name="Post Deployment",
            resolution="2025-01-07T10:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
            history("3", "2025-01-03T10:00:00.000+0000", "9", "Done", "8", "Post Deployment"),
        ]
        metrics = _calc().calculate(_build(issue, histories))

        assert metrics.reopen_count == 0
        assert metrics.is_done is True

    def test_terminal_to_active_is_reopen(self) -> None:
        issue = make_issue("TL-22", created="2025-01-01T09:00:00.000+0000", status_id="9", status_name="Done")
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "9", "Done"),
            history("2", "2025-01-03T10:00:00.000+0000", "9", "Done", "3", "In Progress"),
        ]
        metrics = _calc().calculate(_build(issue, histories))

        assert metrics.reopen_count == 1
        assert metrics.is_reopened is True

    def test_cycle_ends_at_first_terminal(self) -> None:
        issue = make_issue(
            "TL-23",
            created="2025-01-01T09:00:00.000+0000",
            status_id="8",
            status_name="Post Deployment",
            resolution="2025-01-07T10:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
            history("3", "2025-01-05T10:00:00.000+0000", "9", "Done", "8", "Post Deployment"),
        ]
        metrics = _calc().calculate(_build(issue, histories))

        assert metrics.cycle_time_seconds == 24 * 3600
        assert metrics.lead_time_seconds is not None
        assert metrics.lead_time_seconds > metrics.cycle_time_seconds  # type: ignore[operator]


class TestProjectAggregator:
    def test_aggregation(self) -> None:
        from jira_analytics.metrics.aggregator import ProjectAggregator

        issue = make_issue(
            "TL-123",
            created="2025-01-01T09:00:00.000+0000",
            status_id="9",
            status_name="Done",
            resolution="2025-01-05T17:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("4", "2025-01-04T10:00:00.000+0000", "6", "QA IN PROGRESS", "9", "Done"),
        ]
        calc = MetricCalculator(make_workflow())
        issues = [calc.calculate(_build(issue, histories))]
        project, _bug = ProjectAggregator().aggregate("TL", issues, workflow=make_workflow())

        assert project.total_issues == 1
        assert project.done_count == 1
        assert project.throughput == 1
        assert project.median_lead_time_seconds is not None

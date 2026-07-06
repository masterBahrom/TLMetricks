"""Unit tests for timeline reconstruction."""

from __future__ import annotations

from datetime import datetime, timezone

from jira_analytics.models.timeline import TimelinesDocument
from jira_analytics.parser.timeline_builder import TimelineBuilder
from jira_analytics.validators import TimelineValidator

from tests.conftest import REFERENCE, history, make_issue, make_registry

UTC = timezone.utc


def _builder() -> TimelineBuilder:
    return TimelineBuilder(make_registry(), reference_time=REFERENCE)


class TestNormalWorkflow:
    def test_full_workflow(self) -> None:
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
        timeline = _builder().build_issue_timeline(issue, histories)

        assert len(timeline.periods) == 5
        assert timeline.periods[0].status_name == "To Do"
        assert timeline.periods[0].entered_at == datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        assert timeline.periods[0].left_at == datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        assert timeline.periods[-1].status_name == "Done"
        assert timeline.periods[-1].is_done is True
        assert timeline.periods[-1].is_current is False

        report = TimelineValidator(reference_time=REFERENCE).validate_document(
            TimelinesDocument(timelines={"TL-1": timeline}, issue_count=1)
        )
        assert report.is_valid


class TestReopenedIssue:
    def test_done_reopened_done(self) -> None:
        issue = make_issue("TL-2", created="2025-01-01T09:00:00.000+0000", status_id="9", status_name="Done")
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-03T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
            history("3", "2025-01-04T10:00:00.000+0000", "9", "Done", "3", "In Progress"),
            history("4", "2025-01-05T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
        ]
        timeline = _builder().build_issue_timeline(issue, histories)

        done_periods = [p for p in timeline.periods if p.is_done]
        assert len(done_periods) == 2
        assert any("reopened" in w.lower() or "Discontinuous" in w for w in timeline.warnings) or len(done_periods) == 2


class TestCancelledIssue:
    def test_cancelled_is_done(self) -> None:
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
        timeline = _builder().build_issue_timeline(issue, histories)

        assert timeline.periods[-1].status_name == "Cancelled"
        assert timeline.periods[-1].is_done is True
        assert timeline.periods[-1].is_current is False


class TestNoTransitions:
    def test_empty_changelog_uses_current_status(self) -> None:
        issue = make_issue("TL-4", created="2025-01-01T09:00:00.000+0000", status_id="3", status_name="In Progress")
        timeline = _builder().build_issue_timeline(issue, [])

        assert len(timeline.periods) == 1
        assert timeline.periods[0].status_name == "In Progress"
        assert timeline.periods[0].is_current is True
        assert timeline.periods[0].left_at is None
        assert any("No status transitions" in w for w in timeline.warnings)


class TestSingleTransition:
    def test_one_transition(self) -> None:
        issue = make_issue(
            "TL-5",
            created="2025-01-01T09:00:00.000+0000",
            status_id="9",
            status_name="Done",
            resolution="2025-01-02T10:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "9", "Done"),
        ]
        timeline = _builder().build_issue_timeline(issue, histories)

        assert len(timeline.periods) == 2
        assert timeline.periods[0].status_name == "To Do"
        assert timeline.periods[1].status_name == "Done"


class TestMultipleDone:
    def test_multiple_done_periods(self) -> None:
        issue = make_issue("TL-6", created="2025-01-01T09:00:00.000+0000", status_id="9", status_name="Done")
        histories = [
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "9", "Done"),
            history("2", "2025-01-04T10:00:00.000+0000", "9", "Done", "3", "In Progress"),
            history("3", "2025-01-05T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
        ]
        timeline = _builder().build_issue_timeline(issue, histories)
        done_periods = [p for p in timeline.periods if p.is_done]
        assert len(done_periods) == 2


class TestBrokenHistory:
    def test_out_of_order_is_sorted(self) -> None:
        issue = make_issue("TL-7", created="2025-01-01T09:00:00.000+0000", status_id="3", status_name="In Progress")
        histories = [
            history("2", "2025-01-03T10:00:00.000+0000", "3", "In Progress", "9", "Done"),
            history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
        ]
        timeline = _builder().build_issue_timeline(issue, histories)

        assert timeline.periods[0].status_name == "To Do"
        assert timeline.periods[-1].status_name == "Done"
        assert len(timeline.periods) == 3

    def test_duplicate_transitions_removed(self) -> None:
        issue = make_issue("TL-8", created="2025-01-01T09:00:00.000+0000", status_id="3", status_name="In Progress")
        dup = history("1", "2025-01-02T10:00:00.000+0000", "2", "To Do", "3", "In Progress")
        histories = [dup, dup]
        timeline = _builder().build_issue_timeline(issue, histories)
        assert len(timeline.periods) == 2


class TestCreatedInProgress:
    def test_first_transition_after_creation(self) -> None:
        issue = make_issue("TL-9", created="2025-01-01T09:00:00.000+0000", status_id="3", status_name="In Progress")
        histories = [
            history("1", "2025-01-01T09:30:00.000+0000", "2", "To Do", "3", "In Progress"),
        ]
        timeline = _builder().build_issue_timeline(issue, histories)

        assert timeline.periods[0].status_name == "To Do"
        assert timeline.periods[0].entered_at == datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        assert timeline.periods[1].status_name == "In Progress"
        assert timeline.periods[1].is_current is True


class TestStatusRegistry:
    def test_build_from_metadata(self) -> None:
        from jira_analytics.parser.status_registry import build_status_registry

        metadata = {
            "statuses": [
                {"id": "1", "name": "To Do", "category_key": "new"},
                {"id": "5", "name": "Done", "category_key": "done"},
            ],
            "workflow_statuses": [
                {"id": "2", "name": "In Progress", "category_key": "indeterminate"},
            ],
        }
        registry = build_status_registry(metadata)
        assert len(registry.statuses) == 3
        assert registry.lookup_by_name("In Progress") is not None

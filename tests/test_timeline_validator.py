"""Unit tests for timeline validation."""

from __future__ import annotations

from datetime import datetime, timezone

from jira_analytics.models.timeline import IssueTimeline, StatusPeriod, TimelinesDocument
from jira_analytics.validators import TimelineValidator

UTC = timezone.utc
REF = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)


def _period(
    name: str,
    entered: str,
    left: str | None,
    *,
    is_current: bool = False,
    is_done: bool = False,
) -> StatusPeriod:
    return StatusPeriod(
        status_id="1",
        status_name=name,
        status_category="done" if is_done else "new",
        entered_at=datetime.fromisoformat(entered).replace(tzinfo=UTC),
        left_at=datetime.fromisoformat(left).replace(tzinfo=UTC) if left else None,
        duration_seconds=3600,
        duration_hours=1.0,
        is_current=is_current,
        is_done=is_done,
    )


class TestTimelineValidator:
    def test_valid_timeline_passes(self) -> None:
        created = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        timeline = IssueTimeline(
            issue_key="TL-1",
            issue_id="1",
            created_at=created,
            periods=[
                StatusPeriod(
                    status_id="1",
                    status_name="To Do",
                    status_category="new",
                    entered_at=created,
                    left_at=datetime(2025, 1, 2, 9, 0, tzinfo=UTC),
                    duration_seconds=86400,
                    duration_hours=24.0,
                    is_current=False,
                    is_done=False,
                ),
                StatusPeriod(
                    status_id="5",
                    status_name="Done",
                    status_category="done",
                    entered_at=datetime(2025, 1, 2, 9, 0, tzinfo=UTC),
                    left_at=datetime(2025, 1, 3, 9, 0, tzinfo=UTC),
                    duration_seconds=86400,
                    duration_hours=24.0,
                    is_current=False,
                    is_done=True,
                ),
            ],
        )
        doc = TimelinesDocument(timelines={"TL-1": timeline}, issue_count=1)
        report = TimelineValidator(reference_time=REF).validate_document(doc)
        assert report.is_valid

    def test_overlapping_periods_fail(self) -> None:
        created = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        timeline = IssueTimeline(
            issue_key="TL-2",
            issue_id="2",
            created_at=created,
            periods=[
                _period("To Do", "2025-01-01T09:00:00+00:00", "2025-01-03T09:00:00+00:00"),
                _period("Done", "2025-01-02T09:00:00+00:00", "2025-01-04T09:00:00+00:00", is_done=True),
            ],
        )
        doc = TimelinesDocument(timelines={"TL-2": timeline}, issue_count=1)
        report = TimelineValidator(reference_time=REF).validate_document(doc)
        assert not report.is_valid
        assert any(i.code == "OVERLAPPING_PERIODS" for i in report.issues)

    def test_current_period_must_be_open(self) -> None:
        created = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        timeline = IssueTimeline(
            issue_key="TL-3",
            issue_id="3",
            created_at=created,
            periods=[
                StatusPeriod(
                    status_id="2",
                    status_name="In Progress",
                    status_category="indeterminate",
                    entered_at=created,
                    left_at=datetime(2025, 1, 2, 9, 0, tzinfo=UTC),
                    duration_seconds=86400,
                    duration_hours=24.0,
                    is_current=True,
                    is_done=False,
                ),
            ],
        )
        doc = TimelinesDocument(timelines={"TL-3": timeline}, issue_count=1)
        report = TimelineValidator(reference_time=REF).validate_document(doc)
        assert not report.is_valid
        assert any(i.code == "CURRENT_NOT_OPEN" for i in report.issues)

    def test_multiple_current_periods_fail(self) -> None:
        created = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        timeline = IssueTimeline(
            issue_key="TL-4",
            issue_id="4",
            created_at=created,
            periods=[
                StatusPeriod(
                    status_id="1",
                    status_name="To Do",
                    status_category="new",
                    entered_at=created,
                    left_at=None,
                    duration_seconds=100,
                    duration_hours=0.03,
                    is_current=True,
                ),
                StatusPeriod(
                    status_id="2",
                    status_name="In Progress",
                    status_category="indeterminate",
                    entered_at=datetime(2025, 1, 2, 9, 0, tzinfo=UTC),
                    left_at=None,
                    duration_seconds=100,
                    duration_hours=0.03,
                    is_current=True,
                ),
            ],
        )
        doc = TimelinesDocument(timelines={"TL-4": timeline}, issue_count=1)
        report = TimelineValidator(reference_time=REF).validate_document(doc)
        assert not report.is_valid
        assert any(i.code == "MULTIPLE_CURRENT" for i in report.issues)

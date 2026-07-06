"""Timeline utilities for analytics computations."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.timeline import IssueTimeline, StatusPeriod


def end_of_day(day: date) -> datetime:
    """Return UTC end-of-day timestamp for a calendar date."""
    return datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)


def status_at(timeline: IssueTimeline, moment: datetime) -> str | None:
    """Return the status name an issue was in at a given moment."""
    for period in timeline.periods:
        period_end = period.left_at or moment
        if period.entered_at <= moment <= period_end:
            return period.status_name
    if timeline.periods:
        last = timeline.periods[-1]
        if moment >= last.entered_at:
            return last.status_name
    return None


def is_wip_at(timeline: IssueTimeline, moment: datetime, workflow: WorkflowConfig) -> bool:
    """True if issue is non-terminal (active WIP) at the given moment."""
    status = status_at(timeline, moment)
    if not status:
        return False
    return not workflow.is_terminal(status)


def current_aging_seconds(timeline: IssueTimeline, reference: datetime) -> float | None:
    """Compute aging for an open issue from current status entry."""
    if not timeline.periods:
        return None
    current_period = next((period for period in timeline.periods if period.is_current), timeline.periods[-1])
    if workflow_is_terminal_period(current_period):
        return None
    return max(0.0, (reference - current_period.entered_at).total_seconds())


def workflow_is_terminal_period(period: StatusPeriod) -> bool:
    return period.status_category == "done" or period.is_done


def date_range(
    timelines: dict[str, IssueTimeline],
    metrics_done_dates: list[datetime],
    reference: datetime,
) -> tuple[date, date]:
    """Determine the date span for timeline analytics."""
    dates: list[date] = []
    for timeline in timelines.values():
        dates.append(timeline.created_at.date())
        for period in timeline.periods:
            dates.append(period.entered_at.date())
            if period.left_at:
                dates.append(period.left_at.date())
    for done_at in metrics_done_dates:
        dates.append(done_at.date())
    dates.append(reference.date())

    if not dates:
        today = reference.date()
        return today, today
    return min(dates), max(dates)


def iter_days(start: date, end: date):
    """Yield each calendar day from start to end inclusive."""
    current = start
    from datetime import timedelta

    while current <= end:
        yield current
        current += timedelta(days=1)

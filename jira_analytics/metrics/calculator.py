"""Per-issue metric calculation from timelines — single pass per issue."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import IssueMetrics, StatusPeriodMetrics, TimeInStatus
from jira_analytics.models.timeline import IssueTimeline, StatusPeriod
from jira_analytics.utils.stats import seconds_to_days, seconds_to_hours

logger = logging.getLogger(__name__)

TOLERANCE_SECONDS = 2.0


@dataclass
class _IssueAccumulator:
    """Mutable accumulator used during the single-pass timeline scan."""

    time_by_status: dict[str, float] = field(default_factory=dict)
    unique_statuses: set[str] = field(default_factory=set)
    active_seconds: float = 0.0
    buffer_seconds: float = 0.0
    terminal_seconds: float = 0.0
    waiting_seconds: float = 0.0
    first_in_progress_at: datetime | None = None
    first_terminal_at: datetime | None = None
    last_terminal_at: datetime | None = None
    last_terminal_left_at: datetime | None = None
    current_status: str | None = None
    reopen_count: int = 0
    was_in_terminal: bool = False
    status_periods: list[StatusPeriodMetrics] = field(default_factory=list)


class MetricCalculator:
    """
    Compute TL workflow-aware metrics from a single IssueTimeline.

    Cycle time: first In Progress → first terminal.
    Active time: In Progress + Review + QA IN PROGRESS.
    Buffer time: Backlog + To Do + Ready for QA + Ready for Deployment.
    """

    def __init__(self, workflow: WorkflowConfig | None = None) -> None:
        self._workflow = workflow or WorkflowConfig()

    def calculate(self, timeline: IssueTimeline) -> IssueMetrics:
        acc = self._scan_periods(timeline.periods)

        is_done = self._determine_is_complete(timeline, acc)
        done_date = self._determine_completion_date(timeline, acc, is_done)
        completion_at = self._determine_completion_at(timeline, done_date, is_done)

        lead_seconds = self._duration_seconds(timeline.created_at, completion_at) if is_done else None
        if is_done and lead_seconds is not None:
            self._normalize_to_lead_time(acc, lead_seconds)
        cycle_seconds = self._compute_cycle_time(acc, is_done)
        resolution_seconds = (
            self._duration_seconds(timeline.created_at, timeline.resolution_at)
            if timeline.resolution_at is not None
            else (lead_seconds if is_done else None)
        )

        ttfg_seconds = (
            self._duration_seconds(timeline.created_at, acc.first_in_progress_at)
            if acc.first_in_progress_at is not None
            else None
        )

        time_in_status = self._build_time_in_status(acc.time_by_status)

        flow_efficiency = None
        if lead_seconds and lead_seconds > 0:
            flow_efficiency = round(min(100.0, acc.active_seconds / lead_seconds * 100), 4)

        return IssueMetrics(
            issue_key=timeline.issue_key,
            issue_id=timeline.issue_id,
            created_date=timeline.created_at,
            resolution_date=timeline.resolution_at,
            done_date=done_date,
            current_status=acc.current_status,
            is_done=is_done,
            is_reopened=acc.reopen_count > 0,
            reopen_count=acc.reopen_count,
            status_count=len(acc.unique_statuses),
            lead_time_seconds=lead_seconds,
            lead_time_hours=self._to_hours(lead_seconds),
            lead_time_days=self._to_days(lead_seconds),
            cycle_time_seconds=cycle_seconds,
            cycle_time_hours=self._to_hours(cycle_seconds),
            cycle_time_days=self._to_days(cycle_seconds),
            resolution_time_seconds=resolution_seconds,
            resolution_time_hours=self._to_hours(resolution_seconds),
            resolution_time_days=self._to_days(resolution_seconds),
            total_active_time_seconds=acc.active_seconds,
            total_active_time_hours=seconds_to_hours(acc.active_seconds),
            buffer_time_seconds=acc.buffer_seconds,
            buffer_time_hours=seconds_to_hours(acc.buffer_seconds),
            terminal_time_seconds=acc.terminal_seconds,
            terminal_time_hours=seconds_to_hours(acc.terminal_seconds),
            waiting_time_seconds=acc.waiting_seconds,
            waiting_time_hours=seconds_to_hours(acc.waiting_seconds),
            time_to_first_progress_seconds=ttfg_seconds,
            time_to_first_progress_hours=self._to_hours(ttfg_seconds),
            flow_efficiency_percent=flow_efficiency,
            time_in_status=time_in_status,
            status_periods=acc.status_periods,
        )

    def calculate_all(self, timelines: dict[str, IssueTimeline]) -> list[IssueMetrics]:
        return [self.calculate(timeline) for timeline in timelines.values()]

    def _scan_periods(self, periods: list[StatusPeriod]) -> _IssueAccumulator:
        acc = _IssueAccumulator()

        for period in periods:
            acc.unique_statuses.add(period.status_name)
            seconds = max(0.0, period.duration_seconds)
            acc.time_by_status[period.status_name] = (
                acc.time_by_status.get(period.status_name, 0.0) + seconds
            )

            is_terminal = self._workflow.is_terminal(period.status_name)
            is_active = self._workflow.is_work_active(period.status_name, period.status_category)
            is_buffer = self._workflow.is_buffer(period.status_name)

            if is_active:
                acc.active_seconds += seconds
            elif is_buffer:
                acc.buffer_seconds += seconds
            elif is_terminal:
                acc.terminal_seconds += seconds
            else:
                acc.waiting_seconds += seconds

            if self._workflow.is_cycle_start(period.status_name) and acc.first_in_progress_at is None:
                acc.first_in_progress_at = period.entered_at

            if is_terminal:
                if acc.first_terminal_at is None:
                    acc.first_terminal_at = period.entered_at
                acc.last_terminal_at = period.entered_at
                acc.last_terminal_left_at = period.left_at

            if acc.was_in_terminal and not is_terminal:
                acc.reopen_count += 1
            acc.was_in_terminal = is_terminal

            if period.is_current:
                acc.current_status = period.status_name

            acc.status_periods.append(
                StatusPeriodMetrics(
                    status=period.status_name,
                    entered_at=period.entered_at,
                    left_at=period.left_at,
                    duration_seconds=seconds,
                    hours=seconds_to_hours(seconds),
                    category=self._workflow.status_category_label(period.status_name),
                )
            )

        if acc.current_status is None and periods:
            acc.current_status = periods[-1].status_name

        return acc

    def _determine_is_complete(self, timeline: IssueTimeline, acc: _IssueAccumulator) -> bool:
        if timeline.resolution_at is not None:
            return True
        if not timeline.periods:
            return False
        last = timeline.periods[-1]
        return self._workflow.is_terminal(last.status_name) and not last.is_current

    def _determine_completion_date(
        self,
        timeline: IssueTimeline,
        acc: _IssueAccumulator,
        is_done: bool,
    ) -> datetime | None:
        if not is_done:
            return None
        if timeline.resolution_at is not None:
            return timeline.resolution_at
        if acc.last_terminal_left_at is not None:
            return acc.last_terminal_left_at
        return acc.last_terminal_at or acc.first_terminal_at

    @staticmethod
    def _determine_completion_at(
        timeline: IssueTimeline,
        done_date: datetime | None,
        is_done: bool,
    ) -> datetime | None:
        if not is_done:
            return None
        return timeline.resolution_at or done_date

    def _normalize_to_lead_time(self, acc: _IssueAccumulator, lead_seconds: float) -> None:
        """Clip terminal tail when timeline extends past completion (open period to reference time)."""
        total = acc.buffer_seconds + acc.active_seconds + acc.terminal_seconds + acc.waiting_seconds
        if total > lead_seconds + TOLERANCE_SECONDS and acc.terminal_seconds > 0:
            excess = total - lead_seconds
            acc.terminal_seconds = max(0.0, acc.terminal_seconds - excess)

    def _compute_cycle_time(self, acc: _IssueAccumulator, is_done: bool) -> float | None:
        """Cycle Time = first In Progress → first terminal status entry."""
        if not is_done or acc.first_in_progress_at is None or acc.first_terminal_at is None:
            return None
        return max(0.0, (acc.first_terminal_at - acc.first_in_progress_at).total_seconds())

    @staticmethod
    def _duration_seconds(start: datetime, end: datetime | None) -> float | None:
        if end is None:
            return None
        return max(0.0, (end - start).total_seconds())

    @staticmethod
    def _build_time_in_status(time_by_status: dict[str, float]) -> list[TimeInStatus]:
        return [
            TimeInStatus(
                status=name,
                duration_seconds=seconds,
                hours=seconds_to_hours(seconds),
                days=seconds_to_days(seconds),
            )
            for name, seconds in sorted(time_by_status.items())
        ]

    @staticmethod
    def _to_hours(seconds: float | None) -> float | None:
        return seconds_to_hours(seconds) if seconds is not None else None

    @staticmethod
    def _to_days(seconds: float | None) -> float | None:
        return seconds_to_days(seconds) if seconds is not None else None

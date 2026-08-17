"""Per-issue metric calculation from timelines — single pass per issue."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

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
    blocked_seconds: float = 0.0
    terminal_blocked_seconds: float = 0.0
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
        first_terminal = self._first_terminal_at(timeline.periods)
        blocked_intervals = self._productive_blocked_intervals(timeline, first_terminal)
        terminal_blocked_seconds = self._terminal_blocked_seconds(timeline, first_terminal)
        acc = self._scan_periods(timeline.periods, blocked_intervals)
        acc.terminal_blocked_seconds = terminal_blocked_seconds

        is_done = self._determine_is_complete(timeline, acc)
        done_date = self._determine_completion_date(timeline, acc, is_done)
        completion_at = self._determine_completion_at(timeline, done_date, is_done)

        lead_seconds = self._duration_seconds(timeline.created_at, completion_at) if is_done else None
        if is_done and lead_seconds is not None:
            self._normalize_to_lead_time(acc, lead_seconds)
        cycle_seconds = self._compute_cycle_time(acc, is_done)
        net_cycle_seconds = self._compute_net_cycle_time(acc, is_done, blocked_intervals)
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

        net_flow_efficiency = None
        if lead_seconds and lead_seconds > 0:
            net_denominator = lead_seconds - acc.blocked_seconds
            if net_denominator > 0:
                net_flow_efficiency = round(min(100.0, acc.active_seconds / net_denominator * 100), 4)

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
            net_cycle_time_seconds=net_cycle_seconds,
            net_cycle_time_hours=self._to_hours(net_cycle_seconds),
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
            blocked_time_seconds=acc.blocked_seconds,
            blocked_time_hours=seconds_to_hours(acc.blocked_seconds),
            terminal_blocked_time_seconds=acc.terminal_blocked_seconds,
            terminal_blocked_time_hours=seconds_to_hours(acc.terminal_blocked_seconds),
            time_to_first_progress_seconds=ttfg_seconds,
            time_to_first_progress_hours=self._to_hours(ttfg_seconds),
            flow_efficiency_percent=flow_efficiency,
            net_flow_efficiency_percent=net_flow_efficiency,
            time_in_status=time_in_status,
            status_periods=acc.status_periods,
        )

    def calculate_all(self, timelines: dict[str, IssueTimeline]) -> list[IssueMetrics]:
        return [self.calculate(timeline) for timeline in timelines.values()]

    def _scan_periods(
        self,
        periods: list[StatusPeriod],
        blocked_intervals: list[tuple[datetime, datetime]],
    ) -> _IssueAccumulator:
        acc = _IssueAccumulator()

        for period in periods:
            acc.unique_statuses.add(period.status_name)
            seconds = max(0.0, period.duration_seconds)
            period_start = period.entered_at
            period_end = period.left_at or (period.entered_at + timedelta(seconds=seconds))
            blocked_seconds = self._overlap_seconds((period_start, period_end), blocked_intervals)
            net_seconds = max(0.0, seconds - blocked_seconds)
            acc.time_by_status[period.status_name] = (
                acc.time_by_status.get(period.status_name, 0.0) + seconds
            )

            is_terminal = self._workflow.is_terminal(period.status_name)
            is_blocked = self._is_blocked_status(period.status_name) and not is_terminal
            is_active = self._workflow.is_work_active(period.status_name, period.status_category)
            is_buffer = self._workflow.is_buffer(period.status_name)

            if is_blocked:
                acc.blocked_seconds += blocked_seconds
            elif is_active:
                acc.active_seconds += net_seconds
                acc.blocked_seconds += blocked_seconds
            elif is_buffer:
                acc.buffer_seconds += net_seconds
                acc.blocked_seconds += blocked_seconds
            elif is_terminal:
                acc.terminal_seconds += seconds
            else:
                acc.waiting_seconds += net_seconds
                acc.blocked_seconds += blocked_seconds

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

    def _compute_net_cycle_time(
        self,
        acc: _IssueAccumulator,
        is_done: bool,
        blocked_intervals: list[tuple[datetime, datetime]],
    ) -> float | None:
        raw_cycle = self._compute_cycle_time(acc, is_done)
        if raw_cycle is None or acc.first_in_progress_at is None or acc.first_terminal_at is None:
            return None
        blocked_in_cycle = self._overlap_seconds(
            (acc.first_in_progress_at, acc.first_terminal_at),
            blocked_intervals,
        )
        return max(0.0, raw_cycle - blocked_in_cycle)

    def _productive_blocked_intervals(
        self,
        timeline: IssueTimeline,
        first_terminal_at: datetime | None,
    ) -> list[tuple[datetime, datetime]]:
        cutoff = first_terminal_at
        intervals: list[tuple[datetime, datetime]] = []

        for flagged in timeline.flagged_periods:
            end = min(flagged.ended_at, cutoff) if cutoff else flagged.ended_at
            if end > flagged.started_at:
                intervals.append((flagged.started_at, end))

        for period in timeline.periods:
            if not self._is_blocked_status(period.status_name):
                continue
            start = period.entered_at
            end = period.left_at or (start + timedelta(seconds=max(0.0, period.duration_seconds)))
            if cutoff:
                end = min(end, cutoff)
            if end > start:
                intervals.append((start, end))

        return self._merge_intervals(intervals)

    @staticmethod
    def _terminal_blocked_seconds(timeline: IssueTimeline, first_terminal_at: datetime | None) -> float:
        if first_terminal_at is None:
            return 0.0
        intervals = [
            (max(flagged.started_at, first_terminal_at), flagged.ended_at)
            for flagged in timeline.flagged_periods
            if flagged.ended_at > first_terminal_at
        ]
        return sum((end - start).total_seconds() for start, end in MetricCalculator._merge_intervals(intervals))

    def _first_terminal_at(self, periods: list[StatusPeriod]) -> datetime | None:
        for period in periods:
            if self._workflow.is_terminal(period.status_name):
                return period.entered_at
        return None

    @staticmethod
    def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
        valid = sorted((start, end) for start, end in intervals if end > start)
        if not valid:
            return []

        merged = [valid[0]]
        for start, end in valid[1:]:
            previous_start, previous_end = merged[-1]
            if start <= previous_end:
                merged[-1] = (previous_start, max(previous_end, end))
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _overlap_seconds(
        interval: tuple[datetime, datetime],
        others: list[tuple[datetime, datetime]],
    ) -> float:
        start, end = interval
        return sum(
            max(0.0, (min(end, other_end) - max(start, other_start)).total_seconds())
            for other_start, other_end in others
        )

    @staticmethod
    def _is_blocked_status(status_name: str | None) -> bool:
        return bool(status_name and status_name.strip().lower() == "blocked")

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

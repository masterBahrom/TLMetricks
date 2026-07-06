"""Timeline validation — ensures reconstructed timelines are internally consistent."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from jira_analytics.models.timeline import IssueTimeline, StatusPeriod, TimelinesDocument
from jira_analytics.utils.datetime_utils import duration_seconds, utc_now

logger = logging.getLogger(__name__)


@dataclass
class TimelineValidationIssue:
    """A single validation finding for an issue timeline."""

    issue_key: str
    severity: str  # error | warning
    code: str
    message: str


@dataclass
class TimelineValidationReport:
    """Aggregated validation results across all timelines."""

    issue_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    issues: list[TimelineValidationIssue] = field(default_factory=list)

    def add(self, issue_key: str, severity: str, code: str, message: str) -> None:
        self.issues.append(
            TimelineValidationIssue(
                issue_key=issue_key,
                severity=severity,
                code=code,
                message=message,
            )
        )
        if severity == "error":
            self.error_count += 1
        else:
            self.warning_count += 1

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0


class TimelineValidator:
    """Validate reconstructed timelines for continuity and consistency."""

    def __init__(self, reference_time: datetime | None = None) -> None:
        self._reference_time = reference_time or utc_now()

    def validate_document(self, document: TimelinesDocument) -> TimelineValidationReport:
        """Validate all timelines in a document."""
        report = TimelineValidationReport(issue_count=document.issue_count)

        for issue_key, timeline in document.timelines.items():
            self.validate_timeline(issue_key, timeline, report)

        logger.info(
            "Timeline validation: %d errors, %d warnings across %d issues",
            report.error_count,
            report.warning_count,
            report.issue_count,
        )
        return report

    def validate_timeline(
        self,
        issue_key: str,
        timeline: IssueTimeline,
        report: TimelineValidationReport,
    ) -> None:
        """Run all validation checks on a single issue timeline."""
        periods = timeline.periods

        if not periods:
            report.add(issue_key, "error", "EMPTY_TIMELINE", "Timeline has no status periods")
            return

        self._check_first_period_starts_at_creation(issue_key, timeline, report)
        self._check_no_overlaps(issue_key, periods, report)
        self._check_continuity(issue_key, periods, report)
        self._check_no_negative_duration(issue_key, periods, report)
        self._check_finished_periods_have_left_at(issue_key, periods, report)
        self._check_single_current_period(issue_key, periods, report)
        self._check_current_period_open(issue_key, periods, report)
        self._check_status_order_logged(issue_key, periods, report)

        for warning in timeline.warnings:
            report.add(issue_key, "warning", "BUILDER_WARNING", warning)

    def _check_first_period_starts_at_creation(
        self,
        issue_key: str,
        timeline: IssueTimeline,
        report: TimelineValidationReport,
    ) -> None:
        first = timeline.periods[0]
        if first.entered_at != timeline.created_at:
            delta = abs((first.entered_at - timeline.created_at).total_seconds())
            severity = "error" if delta > 1 else "warning"
            report.add(
                issue_key,
                severity,
                "CREATION_MISMATCH",
                f"First period entered_at ({first.entered_at.isoformat()}) "
                f"does not match created_at ({timeline.created_at.isoformat()})",
            )

    def _check_no_overlaps(
        self,
        issue_key: str,
        periods: list[StatusPeriod],
        report: TimelineValidationReport,
    ) -> None:
        for index in range(len(periods) - 1):
            current = periods[index]
            nxt = periods[index + 1]
            if current.left_at is None:
                continue
            if current.left_at > nxt.entered_at:
                report.add(
                    issue_key,
                    "error",
                    "OVERLAPPING_PERIODS",
                    f"Period {index} ({current.status_name}) overlaps period {index + 1} "
                    f"({nxt.status_name})",
                )

    def _check_continuity(
        self,
        issue_key: str,
        periods: list[StatusPeriod],
        report: TimelineValidationReport,
    ) -> None:
        for index in range(len(periods) - 1):
            current = periods[index]
            nxt = periods[index + 1]
            if current.left_at is None:
                report.add(
                    issue_key,
                    "error",
                    "OPEN_NON_FINAL_PERIOD",
                    f"Non-final period {index} ({current.status_name}) has left_at=null",
                )
                continue
            delta = abs((current.left_at - nxt.entered_at).total_seconds())
            if delta > 1:
                report.add(
                    issue_key,
                    "warning",
                    "DISCONTINUOUS_TIMELINE",
                    f"Gap/overlap of {delta:.0f}s between period {index} and {index + 1}",
                )

    def _check_no_negative_duration(
        self,
        issue_key: str,
        periods: list[StatusPeriod],
        report: TimelineValidationReport,
    ) -> None:
        for index, period in enumerate(periods):
            end = period.left_at or self._reference_time
            if duration_seconds(period.entered_at, end) < 0:
                report.add(
                    issue_key,
                    "error",
                    "NEGATIVE_DURATION",
                    f"Period {index} ({period.status_name}) has negative duration",
                )

    def _check_finished_periods_have_left_at(
        self,
        issue_key: str,
        periods: list[StatusPeriod],
        report: TimelineValidationReport,
    ) -> None:
        for index, period in enumerate(periods[:-1]):
            if period.left_at is None:
                report.add(
                    issue_key,
                    "error",
                    "MISSING_LEFT_AT",
                    f"Finished period {index} ({period.status_name}) missing left_at",
                )

    def _check_single_current_period(
        self,
        issue_key: str,
        periods: list[StatusPeriod],
        report: TimelineValidationReport,
    ) -> None:
        current_count = sum(1 for period in periods if period.is_current)
        if current_count > 1:
            report.add(
                issue_key,
                "error",
                "MULTIPLE_CURRENT",
                f"Expected one current period, found {current_count}",
            )

    def _check_current_period_open(
        self,
        issue_key: str,
        periods: list[StatusPeriod],
        report: TimelineValidationReport,
    ) -> None:
        current_periods = [period for period in periods if period.is_current]
        if not current_periods:
            return
        current = current_periods[0]
        if current.left_at is not None:
            report.add(
                issue_key,
                "error",
                "CURRENT_NOT_OPEN",
                f"Current period ({current.status_name}) must have left_at=null",
            )

    def _check_status_order_logged(
        self,
        issue_key: str,
        periods: list[StatusPeriod],
        report: TimelineValidationReport,
    ) -> None:
        """Log informational warnings for unusual status sequences (e.g. reopen)."""
        done_indices = [i for i, period in enumerate(periods) if period.is_done]
        if len(done_indices) >= 2:
            report.add(
                issue_key,
                "warning",
                "REOPENED_ISSUE",
                f"Issue has {len(done_indices)} done periods (likely reopened)",
            )

        if len(periods) == 1:
            report.add(
                issue_key,
                "warning",
                "SINGLE_STATUS",
                f"Issue remained in single status: {periods[0].status_name}",
            )

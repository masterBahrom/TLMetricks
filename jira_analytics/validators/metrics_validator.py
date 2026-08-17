"""Validation for computed issue and project metrics."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from jira_analytics.models.metrics import IssueMetrics, MetricsDocument
from jira_analytics.utils.stats import is_finite

logger = logging.getLogger(__name__)

TOLERANCE_SECONDS = 2.0


@dataclass
class MetricsValidationIssue:
    issue_key: str
    severity: str
    code: str
    message: str


@dataclass
class MetricsValidationReport:
    issue_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    issues: list[MetricsValidationIssue] = field(default_factory=list)

    def add(self, issue_key: str, severity: str, code: str, message: str) -> None:
        self.issues.append(
            MetricsValidationIssue(issue_key=issue_key, severity=severity, code=code, message=message)
        )
        if severity == "error":
            self.error_count += 1
        else:
            self.warning_count += 1

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0


class MetricsValidator:
    """Validate computed metrics for internal consistency."""

    def validate_document(self, document: MetricsDocument) -> MetricsValidationReport:
        report = MetricsValidationReport(issue_count=len(document.issues))

        for issue in document.issues:
            self._validate_issue(issue, report)

        self._validate_project_counts(document, report)
        self._validate_bug_rate(document, report)

        logger.info(
            "Metrics validation: %d errors, %d warnings across %d issues",
            report.error_count,
            report.warning_count,
            report.issue_count,
        )
        return report

    def _validate_issue(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        key = issue.issue_key

        self._check_finite_values(issue, report)
        self._check_non_negative(issue, report)

        if issue.is_done:
            self._check_done_has_lead(issue, report)
            self._check_lead_gte_cycle(issue, report)
            self._check_lead_gte_buffer(issue, report)
            self._check_lead_gte_active(issue, report)
            self._check_buffer_active_lead(issue, report)
        else:
            self._check_open_no_resolution(issue, report)

        if issue.flow_efficiency_percent is not None and issue.flow_efficiency_percent > 100.0 + 0.01:
            report.add(key, "error", "FLOW_EFFICIENCY_HIGH", f"Flow efficiency > 100%: {issue.flow_efficiency_percent}")
        if issue.net_flow_efficiency_percent is not None and issue.net_flow_efficiency_percent > 100.0 + 0.01:
            report.add(
                key,
                "error",
                "NET_FLOW_EFFICIENCY_HIGH",
                f"Net flow efficiency > 100%: {issue.net_flow_efficiency_percent}",
            )

        if issue.cycle_time_seconds is not None and issue.lead_time_seconds is not None:
            if issue.cycle_time_seconds > issue.lead_time_seconds + TOLERANCE_SECONDS:
                report.add(
                    key,
                    "error",
                    "CYCLE_EXCEEDS_LEAD",
                    f"Cycle ({issue.cycle_time_seconds}s) > Lead ({issue.lead_time_seconds}s)",
                )
        if (
            issue.net_cycle_time_seconds is not None
            and issue.cycle_time_seconds is not None
            and issue.net_cycle_time_seconds > issue.cycle_time_seconds + TOLERANCE_SECONDS
        ):
            report.add(key, "error", "NET_CYCLE_EXCEEDS_RAW", "Net Cycle Time exceeds raw Cycle Time")

    def _check_finite_values(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        numeric_fields = [
            issue.lead_time_seconds,
            issue.cycle_time_seconds,
            issue.net_cycle_time_seconds,
            issue.resolution_time_seconds,
            issue.total_active_time_seconds,
            issue.buffer_time_seconds,
            issue.blocked_time_seconds,
            issue.terminal_blocked_time_seconds,
            issue.terminal_time_seconds,
            issue.waiting_time_seconds,
            issue.time_to_first_progress_seconds,
            issue.flow_efficiency_percent,
            issue.net_flow_efficiency_percent,
        ]
        for value in numeric_fields:
            if not is_finite(value):
                report.add(issue.issue_key, "error", "NON_FINITE", f"Non-finite metric value detected: {value}")
                return

    def _check_non_negative(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        for name, value in (
            ("lead_time", issue.lead_time_seconds),
            ("cycle_time", issue.cycle_time_seconds),
            ("net_cycle_time", issue.net_cycle_time_seconds),
            ("buffer_time", issue.buffer_time_seconds),
            ("active_time", issue.total_active_time_seconds),
            ("blocked_time", issue.blocked_time_seconds),
            ("terminal_blocked_time", issue.terminal_blocked_time_seconds),
            ("terminal_time", issue.terminal_time_seconds),
        ):
            if value is not None and value < 0:
                report.add(issue.issue_key, "error", "NEGATIVE_VALUE", f"{name} is negative: {value}")

    def _check_done_has_lead(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        if issue.lead_time_seconds is None:
            report.add(issue.issue_key, "error", "DONE_MISSING_LEAD", "Done issue must have lead_time_seconds")
        if issue.done_date is None:
            report.add(issue.issue_key, "error", "DONE_MISSING_DATE", "Done issue must have done_date")

    def _check_open_no_resolution(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        if issue.resolution_time_seconds is not None:
            report.add(issue.issue_key, "error", "OPEN_HAS_RESOLUTION", "Open issue must not have resolution_time_seconds")

    def _check_lead_gte_cycle(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        if issue.lead_time_seconds is None or issue.cycle_time_seconds is None:
            return
        if issue.cycle_time_seconds > issue.lead_time_seconds + TOLERANCE_SECONDS:
            report.add(issue.issue_key, "error", "CYCLE_EXCEEDS_LEAD", "Cycle exceeds Lead Time")

    def _check_lead_gte_buffer(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        if issue.lead_time_seconds is None:
            return
        if issue.buffer_time_seconds > issue.lead_time_seconds + TOLERANCE_SECONDS:
            report.add(issue.issue_key, "error", "BUFFER_EXCEEDS_LEAD", "Buffer exceeds Lead Time")

    def _check_lead_gte_active(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        if issue.lead_time_seconds is None:
            return
        if issue.total_active_time_seconds > issue.lead_time_seconds + TOLERANCE_SECONDS:
            report.add(issue.issue_key, "error", "ACTIVE_EXCEEDS_LEAD", "Active time exceeds Lead Time")

    def _check_buffer_active_lead(self, issue: IssueMetrics, report: MetricsValidationReport) -> None:
        if issue.lead_time_seconds is None:
            return
        if issue.buffer_time_seconds + issue.total_active_time_seconds > issue.lead_time_seconds + TOLERANCE_SECONDS:
            report.add(
                issue.issue_key,
                "error",
                "BUFFER_ACTIVE_EXCEEDS_LEAD",
                "Buffer + Active exceeds Lead Time",
            )

    def _validate_project_counts(self, document: MetricsDocument, report: MetricsValidationReport) -> None:
        project = document.project
        if project.done_count + project.open_count != project.total_issues:
            report.add("PROJECT", "error", "COUNT_MISMATCH", "done + open != total")
        if project.bug_rate_percent is not None and project.bug_rate_percent > 100.0 + 0.01:
            report.add("PROJECT", "error", "BUG_RATE_HIGH", f"Bug rate > 100%: {project.bug_rate_percent}")

    def _validate_bug_rate(self, document: MetricsDocument, report: MetricsValidationReport) -> None:
        bug = document.bug_analytics
        if bug.completed_issues and bug.bug_rate_percent is not None:
            expected = (bug.total_bugs / bug.completed_issues) * 100
            if abs(expected - bug.bug_rate_percent) > 0.1:
                report.add("PROJECT", "warning", "BUG_RATE_MISMATCH", "Bug rate does not match completed bugs ratio")

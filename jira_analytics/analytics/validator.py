"""Analytics result validation."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from jira_analytics.analytics.models import AnalyticsDocument
from jira_analytics.models.metrics import MetricsDocument

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsValidationIssue:
    severity: str
    code: str
    message: str


@dataclass
class AnalyticsValidationReport:
    error_count: int = 0
    warning_count: int = 0
    issues: list[AnalyticsValidationIssue] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str) -> None:
        self.issues.append(AnalyticsValidationIssue(severity=severity, code=code, message=message))
        if severity == "error":
            self.error_count += 1
        else:
            self.warning_count += 1

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0


class AnalyticsValidator:
    """Validate analytics document for consistency."""

    def validate(
        self,
        analytics: AnalyticsDocument,
        metrics: MetricsDocument,
    ) -> AnalyticsValidationReport:
        report = AnalyticsValidationReport()

        self._check_non_negative(analytics, report)
        self._check_percentages(analytics, report)
        self._check_flow_efficiency(analytics, report)
        self._check_throughput_matches(analytics, metrics, report)
        self._check_aging_open_only(analytics, metrics, report)

        logger.info(
            "Analytics validation: %d errors, %d warnings",
            report.error_count,
            report.warning_count,
        )
        return report

    def _check_non_negative(self, analytics: AnalyticsDocument, report: AnalyticsValidationReport) -> None:
        for entry in analytics.flow.per_issue:
            if entry.efficiency_percent < 0 or entry.active_time_seconds < 0 or entry.lead_time_seconds < 0:
                report.add("error", "NEGATIVE_FLOW", f"Negative flow value for {entry.issue_key}")

        for entry in analytics.aging.top_oldest:
            if entry.aging_seconds < 0:
                report.add("error", "NEGATIVE_AGING", f"Negative aging for {entry.issue_key}")

        for category in analytics.queues.categories:
            if category.total_seconds < 0 or category.percent_of_total < 0:
                report.add("error", "NEGATIVE_QUEUE", f"Negative queue value in {category.category}")

    def _check_percentages(self, analytics: AnalyticsDocument, report: AnalyticsValidationReport) -> None:
        for category in analytics.queues.categories:
            if category.percent_of_total > 100.0 + 0.01:
                report.add(
                    "error",
                    "PERCENT_OVERFLOW",
                    f"Queue percent > 100 for {category.category}: {category.percent_of_total}",
                )

        if analytics.summary.reopen_percent > 100.0:
            report.add("error", "REOPEN_PERCENT", f"Reopen percent > 100: {analytics.summary.reopen_percent}")

    def _check_flow_efficiency(self, analytics: AnalyticsDocument, report: AnalyticsValidationReport) -> None:
        for entry in analytics.flow.per_issue:
            if entry.efficiency_percent > 100.0 + 0.01:
                report.add(
                    "error",
                    "FLOW_EFFICIENCY_OVERFLOW",
                    f"Flow efficiency > 100 for {entry.issue_key}: {entry.efficiency_percent}",
                )

        if analytics.flow.average_efficiency_percent is not None:
            if analytics.flow.average_efficiency_percent > 100.0 + 0.01:
                report.add("error", "FLOW_AVG_OVERFLOW", "Average flow efficiency > 100")

    def _check_throughput_matches(
        self,
        analytics: AnalyticsDocument,
        metrics: MetricsDocument,
        report: AnalyticsValidationReport,
    ) -> None:
        daily_total = sum(bucket.count for bucket in analytics.throughput.daily)
        expected = metrics.project.throughput

        if daily_total != expected:
            report.add(
                "warning",
                "THROUGHPUT_MISMATCH",
                f"Daily throughput sum ({daily_total}) != metrics throughput ({expected})",
            )

        if analytics.summary.total_throughput != expected:
            report.add(
                "error",
                "SUMMARY_THROUGHPUT",
                f"Summary throughput ({analytics.summary.total_throughput}) != metrics ({expected})",
            )

    def _check_aging_open_only(
        self,
        analytics: AnalyticsDocument,
        metrics: MetricsDocument,
        report: AnalyticsValidationReport,
    ) -> None:
        done_keys = {issue.issue_key for issue in metrics.issues if issue.is_done}
        for entry in analytics.aging.top_oldest:
            if entry.issue_key in done_keys:
                report.add(
                    "error",
                    "AGING_DONE_ISSUE",
                    f"Aging computed for completed issue {entry.issue_key}",
                )

        if analytics.aging.open_issue_count != metrics.project.open_count:
            report.add(
                "warning",
                "AGING_COUNT",
                f"Aging open count ({analytics.aging.open_issue_count}) "
                f"!= metrics open count ({metrics.project.open_count})",
            )

        for value in (
            analytics.aging.average_seconds,
            analytics.aging.median_seconds,
            analytics.aging.p90_seconds,
        ):
            if value is not None and (not math.isfinite(value) or value < 0):
                report.add("error", "INVALID_AGING", f"Invalid aging aggregate: {value}")

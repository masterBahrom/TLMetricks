"""Data-quality checks for changelog coverage and timeline reconstruction."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from jira_analytics.models.timeline import TimelinesDocument
from jira_analytics.utils.datetime_utils import parse_jira_datetime

logger = logging.getLogger(__name__)

NO_TRANSITIONS_WARNING = "No status transitions found in changelog; using current status only"


@dataclass
class TimelineDataQualityReport:
    """Aggregated changelog and timeline coverage statistics."""

    total_issues: int = 0
    issues_with_changelog: int = 0
    issues_with_status_transitions: int = 0
    issues_single_period: int = 0
    completed_without_transitions: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def no_transition_rate(self) -> float:
        if self.total_issues == 0:
            return 0.0
        without = self.total_issues - self.issues_with_status_transitions
        return without / self.total_issues

    def log_summary(self) -> None:
        logger.info(
            "Timeline data quality: total=%d changelog=%d transitions=%d single_period=%d "
            "completed_no_transitions=%d",
            self.total_issues,
            self.issues_with_changelog,
            self.issues_with_status_transitions,
            self.issues_single_period,
            self.completed_without_transitions,
        )
        for warning in self.warnings:
            logger.warning("Timeline data quality: %s", warning)


def assess_timeline_data_quality(
    issues: list[dict],
    changelog_by_key: dict[str, list],
    document: TimelinesDocument,
) -> TimelineDataQualityReport:
    """Measure changelog join coverage and flag systemic gaps."""
    report = TimelineDataQualityReport(total_issues=len(document.timelines))

    for issue in issues:
        issue_key = issue.get("key")
        if not issue_key or issue_key not in document.timelines:
            continue

        histories = changelog_by_key.get(str(issue_key), [])
        if histories:
            report.issues_with_changelog += 1

        timeline = document.timelines[issue_key]
        has_transitions = NO_TRANSITIONS_WARNING not in timeline.warnings
        if has_transitions:
            report.issues_with_status_transitions += 1

        if len(timeline.periods) == 1:
            report.issues_single_period += 1

        fields = issue.get("fields", {}) or {}
        is_completed = parse_jira_datetime(fields.get("resolutiondate")) is not None
        if is_completed and not has_transitions:
            report.completed_without_transitions += 1

    without_transitions = report.total_issues - report.issues_with_status_transitions
    if report.total_issues and (without_transitions / report.total_issues) > 0.20:
        pct = without_transitions / report.total_issues * 100
        report.warnings.append(
            f"{without_transitions}/{report.total_issues} issues ({pct:.1f}%) have no status transitions"
        )

    if report.completed_without_transitions:
        report.warnings.append(
            f"{report.completed_without_transitions} completed issue(s) have no status transitions"
        )

    return report

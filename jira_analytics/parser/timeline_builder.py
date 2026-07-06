"""Reconstruct issue lifecycle timelines from cached changelog data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jira_analytics.models.timeline import (
    IssueTimeline,
    StatusPeriod,
    StatusRegistry,
    TimelinesDocument,
)
from jira_analytics.utils.datetime_utils import duration_seconds, parse_jira_datetime, utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StatusTransition:
    """A single status change extracted from changelog history."""

    at: datetime
    history_id: str
    from_id: str | None
    from_name: str | None
    to_id: str | None
    to_name: str | None


class TimelineBuilder:
    """
    Reconstruct complete issue timelines from cached issues and changelogs.

    Uses only Phase 1 cache data — no Jira API calls.
    """

    def __init__(self, registry: StatusRegistry, reference_time: datetime | None = None) -> None:
        self._registry = registry
        self._reference_time = reference_time or utc_now()

    def build_all(
        self,
        issues: list[dict[str, Any]],
        changelog_data: list[dict[str, Any]],
    ) -> TimelinesDocument:
        """Build timelines for every issue in the cache."""
        changelog_by_key = index_changelog_by_issue(changelog_data)
        document = TimelinesDocument(generated_at=self._reference_time)

        for issue in issues:
            issue_key = issue.get("key")
            if not issue_key:
                continue
            timeline = self.build_issue_timeline(
                issue,
                changelog_by_key.get(issue_key, []),
            )
            document.timelines[issue_key] = timeline

        document.issue_count = len(document.timelines)
        logger.info("Built timelines for %d issues", document.issue_count)
        return document

    def build_issue_timeline(
        self,
        issue: dict[str, Any],
        histories: list[dict[str, Any]],
    ) -> IssueTimeline:
        """Reconstruct the lifecycle timeline for a single issue."""
        issue_key = str(issue["key"])
        issue_id = str(issue.get("id", ""))
        fields = issue.get("fields", {})

        created_at = parse_jira_datetime(fields.get("created"))
        if created_at is None:
            created_at = self._reference_time

        resolution_at = parse_jira_datetime(fields.get("resolutiondate"))
        current_status = fields.get("status", {}) or {}

        transitions = deduplicate_transitions(extract_status_transitions(histories))

        warnings: list[str] = []
        if not transitions:
            warnings.append("No status transitions found in changelog; using current status only")

        periods = self._build_periods(
            created_at=created_at,
            resolution_at=resolution_at,
            current_status=current_status,
            transitions=transitions,
            warnings=warnings,
        )

        return IssueTimeline(
            issue_key=issue_key,
            issue_id=issue_id,
            created_at=created_at,
            resolution_at=resolution_at,
            periods=periods,
            warnings=warnings,
        )

    def _build_periods(
        self,
        *,
        created_at: datetime,
        resolution_at: datetime | None,
        current_status: dict[str, Any],
        transitions: list[StatusTransition],
        warnings: list[str],
    ) -> list[StatusPeriod]:
        if not transitions:
            return [self._single_period_from_current(created_at, resolution_at, current_status)]

        periods: list[StatusPeriod] = []
        first = transitions[0]

        if first.at < created_at:
            warnings.append(
                f"First transition at {first.at.isoformat()} predates creation "
                f"{created_at.isoformat()}; clamping to creation time"
            )

        initial_entry = self._registry.resolve(
            first.from_id or str(current_status.get("id", "")),
            first.from_name or current_status.get("name"),
        )
        if not first.from_id and not first.from_name:
            warnings.append("First transition missing 'from' status; using current issue status as fallback")

        first_change_at = max(first.at, created_at)

        # Period from creation until the first recorded status change
        if first_change_at > created_at:
            periods.append(
                self._make_period(
                    status_id=initial_entry.status_id,
                    status_name=initial_entry.status_name,
                    status_category=initial_entry.status_category,
                    entered_at=created_at,
                    left_at=first_change_at,
                    is_current=False,
                )
            )

        for index, transition in enumerate(transitions):
            to_entry = self._registry.resolve(transition.to_id, transition.to_name)
            entered_at = max(transition.at, created_at)
            is_last = index == len(transitions) - 1

            if not is_last:
                left_at = max(transitions[index + 1].at, created_at)
                is_current = False
            else:
                left_at, is_current = self._resolve_final_bounds(
                    to_entry.status_category,
                    entered_at,
                    resolution_at,
                )

            # Warn on discontinuous workflow chain
            if index > 0:
                previous = transitions[index - 1]
                if (
                    previous.to_id != transition.from_id
                    and (previous.to_name or "").lower() != (transition.from_name or "").lower()
                ):
                    warnings.append(
                        f"Discontinuous transition at {entered_at.isoformat()}: "
                        f"expected from {previous.to_name!r}, got {transition.from_name!r}"
                    )

            # Merge consecutive periods in the same status (re-entry creates new period)
            if periods and periods[-1].status_id == to_entry.status_id and periods[-1].left_at == entered_at:
                periods[-1].left_at = left_at
                periods[-1].is_current = is_current
                periods[-1].is_done = to_entry.status_category == "done"
                self._refresh_duration(periods[-1])
                continue

            periods.append(
                self._make_period(
                    status_id=to_entry.status_id,
                    status_name=to_entry.status_name,
                    status_category=to_entry.status_category,
                    entered_at=entered_at,
                    left_at=left_at,
                    is_current=is_current,
                )
            )

        self._enforce_continuity(periods, created_at, warnings)
        self._enforce_single_current(periods, warnings)
        return periods

    def _resolve_final_bounds(
        self,
        status_category: str,
        entered_at: datetime,
        resolution_at: datetime | None,
    ) -> tuple[datetime | None, bool]:
        """Determine left_at and is_current for the final status period."""
        if status_category == "done":
            left_at = resolution_at or entered_at
            return left_at, False
        return None, True

    def _single_period_from_current(
        self,
        created_at: datetime,
        resolution_at: datetime | None,
        current_status: dict[str, Any],
    ) -> StatusPeriod:
        entry = self._registry.resolve(
            str(current_status.get("id", "")),
            current_status.get("name"),
        )
        is_done = entry.status_category == "done"
        left_at = resolution_at if is_done else None
        is_current = not is_done
        return self._make_period(
            status_id=entry.status_id,
            status_name=entry.status_name,
            status_category=entry.status_category,
            entered_at=created_at,
            left_at=left_at,
            is_current=is_current,
        )

    def _make_period(
        self,
        *,
        status_id: str,
        status_name: str,
        status_category: str,
        entered_at: datetime,
        left_at: datetime | None,
        is_current: bool,
    ) -> StatusPeriod:
        end = left_at or self._reference_time
        seconds = duration_seconds(entered_at, end)
        return StatusPeriod(
            status_id=status_id,
            status_name=status_name,
            status_category=status_category,
            entered_at=entered_at,
            left_at=left_at,
            duration_seconds=seconds,
            duration_hours=round(seconds / 3600, 4),
            is_current=is_current,
            is_done=status_category == "done",
        )

    def _refresh_duration(self, period: StatusPeriod) -> None:
        end = period.left_at or self._reference_time
        period.duration_seconds = duration_seconds(period.entered_at, end)
        period.duration_hours = round(period.duration_seconds / 3600, 4)

    def _enforce_continuity(
        self,
        periods: list[StatusPeriod],
        created_at: datetime,
        warnings: list[str],
    ) -> None:
        if not periods:
            return

        if periods[0].entered_at != created_at:
            if periods[0].entered_at < created_at:
                warnings.append("First period starts before issue creation; adjusting to created_at")
            else:
                warnings.append(
                    f"First period starts at {periods[0].entered_at.isoformat()} "
                    f"but issue was created at {created_at.isoformat()}"
                )
            periods[0].entered_at = created_at
            self._refresh_duration(periods[0])

        for index in range(len(periods) - 1):
            current = periods[index]
            nxt = periods[index + 1]

            if current.left_at is None:
                current.left_at = nxt.entered_at
                current.is_current = False
                self._refresh_duration(current)
                continue

            if current.left_at != nxt.entered_at:
                delta = abs((nxt.entered_at - current.left_at).total_seconds())
                if delta > 1:
                    warnings.append(
                        f"Timeline gap/overlap of {delta:.0f}s between period "
                        f"{index} ({current.status_name}) and {index + 1} ({nxt.status_name}); "
                        "aligning boundaries"
                    )
                current.left_at = nxt.entered_at
                self._refresh_duration(current)

            if current.duration_seconds < 0:
                warnings.append(f"Negative duration in period {index}; resetting to zero")
                current.duration_seconds = 0.0
                current.duration_hours = 0.0

    def _enforce_single_current(self, periods: list[StatusPeriod], warnings: list[str]) -> None:
        if not periods:
            return

        current_indices = [i for i, period in enumerate(periods) if period.is_current]
        if len(current_indices) > 1:
            warnings.append(f"Multiple current periods detected ({len(current_indices)}); keeping only the last")
            for index in current_indices[:-1]:
                periods[index].is_current = False
                if periods[index].left_at is None and index + 1 < len(periods):
                    periods[index].left_at = periods[index + 1].entered_at
                    self._refresh_duration(periods[index])

        if not any(period.is_current for period in periods):
            last = periods[-1]
            if last.left_at is None:
                last.is_current = True
                self._refresh_duration(last)


def index_changelog_by_issue(changelog_data: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group raw changelog records by issue key."""
    by_key: dict[str, list[dict[str, Any]]] = {}

    for record in changelog_data:
        issue_key = record.get("issueKey") or record.get("issue_key")
        histories = (
            record.get("changeHistories")
            or record.get("histories")
            or record.get("changelog", {}).get("histories")
            or []
        )

        if issue_key:
            by_key.setdefault(str(issue_key), []).extend(histories)
            continue

        if "items" in record:
            key = record.get("issueKey", "UNKNOWN")
            by_key.setdefault(str(key), []).append(record)

    return by_key


def extract_status_transitions(histories: list[dict[str, Any]]) -> list[StatusTransition]:
    """Extract and sort status transitions from changelog histories."""
    transitions: list[StatusTransition] = []

    for history in histories:
        history_id = str(history.get("id", ""))
        created = parse_jira_datetime(history.get("created"))
        if created is None:
            continue

        for item in history.get("items", []):
            field = item.get("field") or item.get("fieldId") or ""
            if field != "status":
                continue

            from_id = item.get("from")
            from_name = item.get("fromString")
            to_id = item.get("to")
            to_name = item.get("toString")

            if from_id == to_id and from_name == to_name:
                continue

            transitions.append(
                StatusTransition(
                    at=created,
                    history_id=history_id,
                    from_id=str(from_id) if from_id is not None else None,
                    from_name=from_name,
                    to_id=str(to_id) if to_id is not None else None,
                    to_name=to_name,
                )
            )

    transitions.sort(key=lambda transition: (transition.at, transition.history_id))
    return transitions


def deduplicate_transitions(transitions: list[StatusTransition]) -> list[StatusTransition]:
    """Remove exact duplicate transitions at the same timestamp."""
    seen: set[tuple[str, str | None, str | None, str | None, str | None]] = set()
    unique: list[StatusTransition] = []

    for transition in transitions:
        key = (
            transition.at.isoformat(),
            transition.from_id,
            transition.from_name,
            transition.to_id,
            transition.to_name,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(transition)

    return unique

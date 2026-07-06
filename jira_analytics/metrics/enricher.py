"""Extract Jira issue metadata from Phase 1 cache and merge into IssueMetrics."""

from __future__ import annotations

import logging
from typing import Any

from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import IssueMetrics
from jira_analytics.utils.datetime_utils import parse_jira_datetime

logger = logging.getLogger(__name__)


def _display_name(user: dict[str, Any] | None) -> str | None:
    if not user:
        return None
    return user.get("displayName") or user.get("name")


def _named(obj: dict[str, Any] | None) -> str | None:
    if not obj:
        return None
    return obj.get("name")


def _story_points(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sprint_name(value: Any) -> str | None:
    """Return the most recent sprint name from Jira sprint field values."""
    if not value:
        return None
    if isinstance(value, dict):
        return value.get("name")
    if isinstance(value, list):
        names = [item.get("name") for item in value if isinstance(item, dict) and item.get("name")]
        if not names:
            return None
        return names[-1]
    if isinstance(value, str):
        return value
    return None


def _components(value: Any) -> list[str]:
    if not value:
        return []
    if not isinstance(value, list):
        return []
    return [item.get("name") for item in value if isinstance(item, dict) and item.get("name")]


def _labels(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _project_key(fields: dict[str, Any], issue_key: str, fallback: str) -> str:
    project = fields.get("project")
    if isinstance(project, dict) and project.get("key"):
        return str(project["key"])
    if "-" in issue_key:
        return issue_key.split("-", 1)[0]
    return fallback


def extract_issue_metadata(
    raw_issue: dict[str, Any],
    *,
    project_key: str,
    story_points_field_id: str | None = None,
    sprint_field_id: str | None = None,
) -> dict[str, Any]:
    """Map a raw Jira issue dict to IssueMetrics metadata fields."""
    fields = raw_issue.get("fields") or {}
    story_field = story_points_field_id or "customfield_10030"
    sprint_field = sprint_field_id or "customfield_10020"

    created = parse_jira_datetime(fields.get("created"))
    resolution_date = parse_jira_datetime(fields.get("resolutiondate"))

    return {
        "summary": fields.get("summary"),
        "description": fields.get("description"),
        "assignee": _display_name(fields.get("assignee")),
        "reporter": _display_name(fields.get("reporter")),
        "issue_type": _named(fields.get("issuetype")),
        "priority": _named(fields.get("priority")),
        "story_points": _story_points(fields.get(story_field)),
        "sprint": _sprint_name(fields.get(sprint_field)),
        "labels": _labels(fields.get("labels")),
        "components": _components(fields.get("components")),
        "created_date": created,
        "resolution": _named(fields.get("resolution")),
        "resolution_date": resolution_date,
        "project_key": _project_key(fields, raw_issue.get("key", ""), project_key),
    }


class IssueMetadataEnricher:
    """
    Merge Jira fields from issues.json into computed IssueMetrics.

    This is the only place in the pipeline that reads issues.json.
    Downstream consumers use metrics.json exclusively.
    """

    def __init__(
        self,
        issues: list[dict[str, Any]],
        metadata: dict[str, Any],
        *,
        project_key: str,
        workflow: WorkflowConfig | None = None,
    ) -> None:
        self._issues_by_key = {issue["key"]: issue for issue in issues if issue.get("key")}
        self._project_key = project_key
        self._workflow = workflow or WorkflowConfig()
        story_field = metadata.get("story_points_field") or {}
        sprint_field = metadata.get("sprint_field") or {}
        self._story_points_field_id = story_field.get("id")
        self._sprint_field_id = sprint_field.get("id")
        self._missing_keys: set[str] = set()

    @property
    def missing_issue_count(self) -> int:
        return len(self._missing_keys)

    def enrich_all(self, metrics: list[IssueMetrics]) -> list[IssueMetrics]:
        enriched: list[IssueMetrics] = []
        for item in metrics:
            enriched.append(self.enrich(item))
        if self._missing_keys:
            logger.warning(
                "No issues.json entry for %d issue(s): %s",
                len(self._missing_keys),
                ", ".join(sorted(self._missing_keys)[:5]),
            )
        return enriched

    def enrich(self, metrics: IssueMetrics) -> IssueMetrics:
        raw = self._issues_by_key.get(metrics.issue_key)
        if raw is None:
            self._missing_keys.add(metrics.issue_key)
            return metrics.model_copy(update={"project_key": self._project_key})

        meta = extract_issue_metadata(
            raw,
            project_key=self._project_key,
            story_points_field_id=self._story_points_field_id,
            sprint_field_id=self._sprint_field_id,
        )
        meta["is_bug"] = self._workflow.is_bug_type(meta.get("issue_type"))
        return metrics.model_copy(update=meta)

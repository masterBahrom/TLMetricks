"""Shared test fixtures for timeline tests."""

from __future__ import annotations

from datetime import datetime, timezone

from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.timeline import StatusRegistry, StatusRegistryEntry

UTC = timezone.utc

REFERENCE = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


def make_workflow() -> WorkflowConfig:
    """TL engineering workflow for tests."""
    return WorkflowConfig(
        terminal_statuses=["Post Deployment", "Done"],
        cancelled_statuses=["Cancelled"],
        queue_statuses=["Backlog", "To Do", "Ready for QA", "Ready for Deployment"],
        active_statuses=["In Progress"],
        review_statuses=["Review"],
        qa_statuses=["QA IN PROGRESS"],
        deployment_queue_statuses=["Ready for Deployment"],
        waiting_statuses=["Waiting", "Blocked"],
        bug_issue_types=["Bug", "HOT-FIX"],
    )


def make_registry() -> StatusRegistry:
    """TL status registry for tests."""
    statuses = {
        "1": StatusRegistryEntry(status_id="1", status_name="Backlog", status_category="new"),
        "2": StatusRegistryEntry(status_id="2", status_name="To Do", status_category="new"),
        "3": StatusRegistryEntry(status_id="3", status_name="In Progress", status_category="indeterminate"),
        "4": StatusRegistryEntry(status_id="4", status_name="Review", status_category="indeterminate"),
        "5": StatusRegistryEntry(status_id="5", status_name="Ready for QA", status_category="new"),
        "6": StatusRegistryEntry(status_id="6", status_name="QA IN PROGRESS", status_category="indeterminate"),
        "7": StatusRegistryEntry(status_id="7", status_name="Ready for Deployment", status_category="new"),
        "8": StatusRegistryEntry(status_id="8", status_name="Post Deployment", status_category="done"),
        "9": StatusRegistryEntry(status_id="9", status_name="Done", status_category="done"),
        "10": StatusRegistryEntry(status_id="10", status_name="Cancelled", status_category="done"),
    }
    return StatusRegistry(statuses=statuses)


def make_issue(
    key: str,
    *,
    created: str,
    status_id: str = "2",
    status_name: str = "To Do",
    resolution: str | None = None,
    summary: str | None = None,
    assignee: str | None = None,
    issue_type: str = "Task",
    priority: str = "Medium",
) -> dict:
    fields: dict = {
        "created": created,
        "status": {"id": status_id, "name": status_name},
        "summary": summary or f"Test issue {key}",
        "issuetype": {"id": "10007", "name": issue_type},
        "priority": {"id": "3", "name": priority},
        "labels": [],
        "components": [],
        "reporter": {"displayName": "Test Reporter"},
        "customfield_10020": None,
        "customfield_10030": None,
    }
    if assignee:
        fields["assignee"] = {"displayName": assignee}
    if resolution:
        fields["resolutiondate"] = resolution
        fields["resolution"] = {"name": "Done"}
    return {"id": "10001", "key": key, "fields": fields}


def history(history_id: str, created: str, from_id: str, from_name: str, to_id: str, to_name: str) -> dict:
    return {
        "id": history_id,
        "created": created,
        "items": [
            {
                "field": "status",
                "from": from_id,
                "fromString": from_name,
                "to": to_id,
                "toString": to_name,
            }
        ],
    }

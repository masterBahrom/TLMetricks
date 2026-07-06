"""Build a status registry from Phase 1 metadata."""

from __future__ import annotations

import logging
from typing import Any

from jira_analytics.models.timeline import StatusRegistry, StatusRegistryEntry
from jira_analytics.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"new", "indeterminate", "done", "undefined"}


def build_status_registry(metadata: dict[str, Any]) -> StatusRegistry:
    """
    Build a status registry from cached metadata.json.

    Merges global statuses and project workflow statuses, preferring
    workflow-specific entries when ids collide.
    """
    registry = StatusRegistry(generated_at=utc_now())
    seen_ids: set[str] = set()

    for source_name, status_list in (
        ("statuses", metadata.get("statuses", [])),
        ("workflow_statuses", metadata.get("workflow_statuses", [])),
    ):
        for raw in status_list:
            entry = _parse_status(raw)
            if not entry:
                continue
            if entry.status_id in seen_ids and source_name == "statuses":
                continue
            registry.statuses[entry.status_id] = entry
            seen_ids.add(entry.status_id)

    logger.info("Built status registry with %d statuses", len(registry.statuses))
    return registry


def _parse_status(raw: dict[str, Any]) -> StatusRegistryEntry | None:
    status_id = raw.get("id")
    status_name = raw.get("name")
    if not status_id or not status_name:
        return None

    category_key = raw.get("category_key") or "undefined"
    if category_key not in VALID_CATEGORIES:
        category_key = _normalize_category(category_key)

    return StatusRegistryEntry(
        status_id=str(status_id),
        status_name=str(status_name),
        status_category=category_key,
    )


def _normalize_category(category_key: str) -> str:
    lowered = category_key.lower()
    if lowered in VALID_CATEGORIES:
        return lowered
    if lowered in {"todo", "to do", "new"}:
        return "new"
    if lowered in {"in progress", "in_progress", "indeterminate"}:
        return "indeterminate"
    if lowered in {"complete", "completed"}:
        return "done"
    return "undefined"

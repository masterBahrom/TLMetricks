"""Discover Jira fields, statuses, boards, and workflow metadata."""

from __future__ import annotations

import logging
from typing import Any

from jira_analytics.jira.client import JiraClient, JiraClientError
from jira_analytics.models import BoardInfo, FieldInfo, ProjectMetadata, StatusInfo

logger = logging.getLogger(__name__)

STORY_POINTS_NAMES = {"Story Points", "Story point estimate", "Story points"}
SPRINT_SCHEMA = "com.pyxis.greenhopper.jira:gh-sprint"
STORY_POINTS_SCHEMA = "com.atlassian.jira.plugin.system.customfieldtypes:float"


class MetadataLoader:
    """Discover and assemble project metadata from Jira APIs."""

    def __init__(self, client: JiraClient, project_key: str, jira_url: str) -> None:
        self._client = client
        self._project_key = project_key
        self._jira_url = jira_url

    def discover(self) -> ProjectMetadata:
        """Run full metadata discovery for the configured project."""
        logger.info("Discovering metadata for project %s", self._project_key)

        fields = self._discover_fields()
        story_points = self._find_story_points_field(fields)
        sprint = self._find_sprint_field(fields)
        statuses = self._discover_statuses()
        workflow_statuses = self._discover_workflow_statuses()
        boards = self._discover_boards()
        board_config = self._discover_board_configuration(boards)

        # Refine story points from board config if available
        if board_config and not story_points:
            story_points = self._story_points_from_board_config(board_config, fields)

        metadata = ProjectMetadata(
            project_key=self._project_key,
            jira_url=self._jira_url,
            story_points_field=story_points,
            sprint_field=sprint,
            fields=fields,
            statuses=statuses,
            workflow_statuses=workflow_statuses,
            boards=boards,
            board_configuration=board_config,
        )

        logger.info(
            "Metadata discovered: %d fields, %d statuses, %d boards",
            len(fields),
            len(statuses),
            len(boards),
        )
        if story_points:
            logger.info("Story Points field: %s (%s)", story_points.name, story_points.id)
        if sprint:
            logger.info("Sprint field: %s (%s)", sprint.name, sprint.id)

        return metadata

    def _discover_fields(self) -> list[FieldInfo]:
        raw_fields: list[dict[str, Any]] = self._client.get("/rest/api/3/field")
        return [
            FieldInfo(
                id=item["id"],
                name=item.get("name", ""),
                custom=item.get("custom", False),
                field_schema=item.get("schema"),
            )
            for item in raw_fields
        ]

    def _find_story_points_field(self, fields: list[FieldInfo]) -> FieldInfo | None:
        for field in fields:
            if field.name in STORY_POINTS_NAMES:
                return field
        for field in fields:
            schema = field.field_schema or {}
            if schema.get("custom") == STORY_POINTS_SCHEMA and "story" in field.name.lower():
                return field
        return None

    def _find_sprint_field(self, fields: list[FieldInfo]) -> FieldInfo | None:
        for field in fields:
            schema = field.field_schema or {}
            if schema.get("custom") == SPRINT_SCHEMA:
                return field
        for field in fields:
            if field.name.lower() == "sprint":
                return field
        return None

    def _discover_statuses(self) -> list[StatusInfo]:
        raw_statuses: list[dict[str, Any]] = self._client.get("/rest/api/3/status")
        return [self._parse_status(item) for item in raw_statuses]

    def _discover_workflow_statuses(self) -> list[StatusInfo]:
        try:
            data: list[dict[str, Any]] = self._client.get(
                f"/rest/api/3/project/{self._project_key}/statuses"
            )
        except JiraClientError as exc:
            logger.warning("Could not fetch project workflow statuses: %s", exc)
            return []

        statuses: list[StatusInfo] = []
        for issue_type_block in data:
            for status in issue_type_block.get("statuses", []):
                parsed = self._parse_status(status)
                if not any(s.id == parsed.id for s in statuses):
                    statuses.append(parsed)
        return statuses

    def _discover_boards(self) -> list[BoardInfo]:
        try:
            data = self._client.get(
                "/rest/agile/1.0/board",
                params={"projectKeyOrId": self._project_key},
            )
        except JiraClientError as exc:
            logger.warning("Could not fetch boards (Agile API may be unavailable): %s", exc)
            return []

        values = data.get("values", [])
        return [
            BoardInfo(
                id=board["id"],
                name=board.get("name", ""),
                type=board.get("type"),
            )
            for board in values
        ]

    def _discover_board_configuration(self, boards: list[BoardInfo]) -> dict[str, Any] | None:
        if not boards:
            return None

        board_id = boards[0].id
        try:
            return self._client.get(f"/rest/agile/1.0/board/{board_id}/configuration")
        except JiraClientError as exc:
            logger.warning("Could not fetch board configuration for board %d: %s", board_id, exc)
            return None

    @staticmethod
    def _story_points_from_board_config(
        board_config: dict[str, Any],
        fields: list[FieldInfo],
    ) -> FieldInfo | None:
        estimation = board_config.get("estimation", {})
        field_ref = estimation.get("field", {})
        field_id = field_ref.get("fieldId")
        if not field_id:
            return None

        field_id_str = f"customfield_{field_id}" if not str(field_id).startswith("customfield_") else str(field_id)
        for field in fields:
            if field.id == field_id_str:
                return field

        return FieldInfo(
            id=field_id_str,
            name=field_ref.get("displayName", "Story Points"),
            custom=True,
        )

    @staticmethod
    def _parse_status(raw: dict[str, Any]) -> StatusInfo:
        category = raw.get("statusCategory", {}) or {}
        return StatusInfo(
            id=str(raw.get("id", "")),
            name=raw.get("name", ""),
            category_key=category.get("key"),
            category_name=category.get("name"),
        )

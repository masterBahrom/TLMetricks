"""JSON validation utilities — no transformation or metrics."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when cached JSON fails structural validation."""


class JsonValidator:
    """Validate structure of cached Jira data without transforming it."""

    def validate_issues(self, issues: Any) -> None:
        """Ensure issues payload is a list of dicts with required keys."""
        if not isinstance(issues, list):
            raise ValidationError("issues.json must contain a JSON array")

        for index, issue in enumerate(issues):
            if not isinstance(issue, dict):
                raise ValidationError(f"Issue at index {index} is not an object")
            if "id" not in issue and "key" not in issue:
                raise ValidationError(f"Issue at index {index} missing 'id' or 'key'")

        logger.debug("Validated %d issues", len(issues))

    def validate_changelog(self, changelog: Any) -> None:
        """Ensure changelog payload is a non-empty list of dicts."""
        if not isinstance(changelog, list):
            raise ValidationError("changelog.json must contain a JSON array")

        for index, entry in enumerate(changelog):
            if not isinstance(entry, dict):
                raise ValidationError(f"Changelog entry at index {index} is not an object")

        logger.debug("Validated %d changelog records", len(changelog))

    def validate_metadata(self, metadata: Any) -> None:
        """Ensure metadata payload has required top-level keys."""
        if not isinstance(metadata, dict):
            raise ValidationError("metadata.json must contain a JSON object")

        required = ("project_key", "jira_url")
        missing = [key for key in required if key not in metadata]
        if missing:
            raise ValidationError(f"metadata.json missing keys: {', '.join(missing)}")

        logger.debug("Validated metadata for project %s", metadata.get("project_key"))

    def validate_manifest(self, manifest: Any) -> None:
        """Ensure manifest payload has required sync fields."""
        if not isinstance(manifest, dict):
            raise ValidationError("manifest.json must contain a JSON object")

        required = ("sync_date", "project", "jql", "issue_count", "changelog_count")
        missing = [key for key in required if key not in manifest]
        if missing:
            raise ValidationError(f"manifest.json missing keys: {', '.join(missing)}")

        logger.debug("Validated manifest for project %s", manifest.get("project"))

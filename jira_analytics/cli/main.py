"""CLI orchestration for Phase 1 sync."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from jira_analytics.cache import CacheStore
from jira_analytics.config import load_config
from jira_analytics.config.loader import ConfigError
from jira_analytics.jira.client import JiraAuthError, JiraClient, JiraClientError
from jira_analytics.loader import ChangelogLoader, IssueLoader, MetadataLoader
from jira_analytics.models import SyncManifest
from jira_analytics.parser import JsonValidator, ValidationError
from jira_analytics.utils import setup_logging

logger = logging.getLogger(__name__)


def main() -> int:
    """Run the Phase 1 sync pipeline."""
    setup_logging()
    logger.info("Jira Analytics — Phase 1 Sync")

    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    cache = CacheStore(config.cache_dir)
    validator = JsonValidator()

    try:
        with JiraClient(config.jira_url, config.email, config.api_token) as client:
            user = client.verify_connection()
            display_name = user.get("displayName", config.email)
            print(f"Connected to Jira as {display_name}")
            print(f"URL: {config.jira_url}")

            # 1. Metadata discovery
            metadata_loader = MetadataLoader(client, config.project_key, config.jira_url)
            metadata = metadata_loader.discover()
            cache.save_metadata(metadata)

            board_name = metadata.boards[0].name if metadata.boards else "N/A"
            board_id = metadata.boards[0].id if metadata.boards else None
            print(f"Project: {config.project_key}")
            print(f"Board: {board_name}")

            # 2. Issue download
            extra_fields: list[str] = []
            if metadata.story_points_field:
                extra_fields.append(metadata.story_points_field.id)
            if metadata.sprint_field:
                extra_fields.append(metadata.sprint_field.id)

            issue_loader = IssueLoader(client)
            issues = issue_loader.load(config.jql, extra_fields=extra_fields or None)
            cache.save_issues(issues)
            validator.validate_issues(issues)

            issue_keys = [issue["key"] for issue in issues if "key" in issue]

            # 3. Changelog download
            changelog_loader = ChangelogLoader(client)
            changelog = changelog_loader.load(issue_keys)
            cache.save_changelog(changelog)
            validator.validate_changelog(changelog)

            changelog_count = ChangelogLoader.count_changelog_entries(changelog)

            # 4. Manifest
            manifest = SyncManifest(
                sync_date=datetime.now(timezone.utc),
                project=config.project_key,
                jql=config.jql,
                issue_count=len(issues),
                changelog_count=changelog_count,
                board_name=board_name if board_name != "N/A" else None,
                board_id=board_id,
            )
            cache.save_manifest(manifest)
            validator.validate_metadata(metadata.model_dump(mode="json"))
            validator.validate_manifest(manifest.model_dump(mode="json"))

            print(f"Issues downloaded: {len(issues)}")
            print(f"Changelog entries: {changelog_count}")
            print(f"Cache saved to: {config.cache_dir.resolve()}")
            print("Cache saved.")

    except JiraAuthError as exc:
        logger.error("Authentication failed: %s", exc)
        return 1
    except JiraClientError as exc:
        logger.error("Jira API error: %s", exc)
        return 1
    except ValidationError as exc:
        logger.error("Validation error: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.warning("Sync interrupted by user")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())

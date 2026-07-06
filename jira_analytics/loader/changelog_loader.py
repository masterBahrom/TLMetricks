"""Download full changelogs for all issues."""

from __future__ import annotations

import logging
from typing import Any

from tqdm import tqdm

from jira_analytics.jira.client import JiraClient, JiraClientError

logger = logging.getLogger(__name__)

BULK_CHANGELOG_BATCH_SIZE = 1000


class ChangelogLoader:
    """Download complete changelogs using dedicated changelog APIs."""

    def __init__(self, client: JiraClient) -> None:
        self._client = client

    def load(self, issue_keys: list[str]) -> list[dict[str, Any]]:
        """
        Download full changelog history for every issue.

        Tries bulk changelog API first (1000 issues per batch).
        Falls back to per-issue changelog API if bulk is unavailable.
        """
        if not issue_keys:
            return []

        logger.info("Downloading changelogs for %d issues", len(issue_keys))

        try:
            return self._load_bulk(issue_keys)
        except JiraClientError as exc:
            logger.warning(
                "Bulk changelog API failed (%s); falling back to per-issue API",
                exc,
            )
            return self._load_per_issue(issue_keys)

    def _load_bulk(self, issue_keys: list[str]) -> list[dict[str, Any]]:
        all_entries: list[dict[str, Any]] = []

        batches = [
            issue_keys[i : i + BULK_CHANGELOG_BATCH_SIZE]
            for i in range(0, len(issue_keys), BULK_CHANGELOG_BATCH_SIZE)
        ]

        for batch in tqdm(batches, desc="Downloading changelogs", unit="batch"):
            entries = self._client.bulk_fetch_changelogs(batch)
            all_entries.extend(entries)

        if not all_entries:
            # Bulk API may return empty for some tenants; verify with single issue
            logger.warning("Bulk changelog returned no entries; trying per-issue fallback")
            return self._load_per_issue(issue_keys)

        logger.info("Downloaded %d changelog entries (bulk)", len(all_entries))
        return all_entries

    def _load_per_issue(self, issue_keys: list[str]) -> list[dict[str, Any]]:
        all_entries: list[dict[str, Any]] = []

        for key in tqdm(issue_keys, desc="Downloading changelogs", unit="issue"):
            histories = self._client.get_issue_changelog(key)
            all_entries.append(
                {
                    "issueKey": key,
                    "histories": histories,
                }
            )

        total_histories = sum(
            len(entry.get("histories", [])) for entry in all_entries
        )
        logger.info(
            "Downloaded %d changelog histories across %d issues (per-issue)",
            total_histories,
            len(all_entries),
        )
        return all_entries

    @staticmethod
    def count_changelog_entries(changelog_data: list[dict[str, Any]]) -> int:
        """Count total changelog history entries across all stored records."""
        count = 0
        for entry in changelog_data:
            if "changeHistories" in entry:
                count += len(entry["changeHistories"])
            elif "histories" in entry:
                count += len(entry["histories"])
            elif "changelog" in entry:
                count += len(entry.get("changelog", {}).get("histories", []))
            elif "history" in entry or "items" in entry:
                count += 1
        return count

"""Download full changelogs for all issues."""

from __future__ import annotations

import logging
from typing import Any

from tqdm import tqdm

from jira_analytics.jira.client import JiraClient, JiraClientError

logger = logging.getLogger(__name__)

BULK_CHANGELOG_BATCH_SIZE = 1000


def returned_issue_keys(
    entries: list[dict[str, Any]],
    key_to_id: dict[str, str],
) -> set[str]:
    """Resolve issue keys present in bulk or per-issue changelog records."""
    id_to_key = {str(issue_id): key for key, issue_id in key_to_id.items()}
    keys: set[str] = set()

    for entry in entries:
        for field in ("issueKey", "issue_key", "key"):
            value = entry.get(field)
            if value:
                keys.add(str(value))
                break
        else:
            for field in ("issueId", "issue_id", "id"):
                raw_id = entry.get(field)
                if raw_id is not None and str(raw_id) in id_to_key:
                    keys.add(id_to_key[str(raw_id)])
                    break

    return keys


def missing_requested_keys(
    issue_keys: list[str],
    entries: list[dict[str, Any]],
    key_to_id: dict[str, str],
) -> list[str]:
    """Issue keys requested but absent from changelog download results."""
    present = returned_issue_keys(entries, key_to_id)
    return [key for key in issue_keys if key not in present]


class ChangelogLoader:
    """Download complete changelogs using dedicated changelog APIs."""

    def __init__(
        self,
        client: JiraClient,
        *,
        enable_per_issue_fallback: bool = False,
    ) -> None:
        self._client = client
        self._enable_per_issue_fallback = enable_per_issue_fallback

    def load(
        self,
        issue_keys: list[str],
        *,
        key_to_id: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Download full changelog history for every issue.

        Tries bulk changelog API first (1000 issues per batch).
        Falls back to per-issue changelog API if bulk is unavailable.
        """
        if not issue_keys:
            return []

        lookup = key_to_id or {key: key for key in issue_keys}

        logger.info("Downloading changelogs for %d issues", len(issue_keys))

        try:
            entries = self._load_bulk(issue_keys, lookup)
        except JiraClientError as exc:
            logger.warning(
                "Bulk changelog API failed (%s); falling back to per-issue API",
                exc,
            )
            return self._load_per_issue(issue_keys)

        return self._apply_missing_key_fallback(issue_keys, entries, lookup)

    def _load_bulk(
        self,
        issue_keys: list[str],
        key_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        all_entries: list[dict[str, Any]] = []

        batches = [
            issue_keys[i : i + BULK_CHANGELOG_BATCH_SIZE]
            for i in range(0, len(issue_keys), BULK_CHANGELOG_BATCH_SIZE)
        ]

        for batch in tqdm(batches, desc="Downloading changelogs", unit="batch"):
            entries = self._client.bulk_fetch_changelogs(batch)
            all_entries.extend(entries)

        if not all_entries:
            logger.warning("Bulk changelog returned no entries; trying per-issue fallback")
            return self._load_per_issue(issue_keys)

        self._log_missing_keys(issue_keys, all_entries, key_to_id)
        logger.info("Downloaded %d changelog issue records (bulk)", len(all_entries))
        return all_entries

    def _log_missing_keys(
        self,
        issue_keys: list[str],
        entries: list[dict[str, Any]],
        key_to_id: dict[str, str],
    ) -> None:
        missing = missing_requested_keys(issue_keys, entries, key_to_id)
        if not missing:
            logger.info("Bulk changelog coverage: %d/%d issues", len(issue_keys), len(issue_keys))
            return

        sample = ", ".join(missing[:10])
        if len(missing) > 10:
            sample += ", ..."
        logger.warning(
            "Bulk changelog missing %d/%d requested issues (may have no changelog): %s",
            len(missing),
            len(issue_keys),
            sample,
        )

    def _apply_missing_key_fallback(
        self,
        issue_keys: list[str],
        entries: list[dict[str, Any]],
        key_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        missing = missing_requested_keys(issue_keys, entries, key_to_id)
        if not missing:
            return entries

        if not self._enable_per_issue_fallback:
            return entries

        logger.info("Per-issue fallback for %d missing changelog keys", len(missing))
        for key in tqdm(missing, desc="Fallback changelogs", unit="issue"):
            histories = self._client.get_issue_changelog(key)
            entries.append(
                {
                    "issueKey": key,
                    "histories": histories,
                }
            )
        return entries

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

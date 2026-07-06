"""Download all issues matching the configured JQL."""

from __future__ import annotations

import logging
from typing import Any

from tqdm import tqdm

from jira_analytics.jira.client import JiraClient

logger = logging.getLogger(__name__)

BULK_FETCH_BATCH_SIZE = 100

# Fields needed for future phases; kept minimal for Phase 1
DEFAULT_ISSUE_FIELDS = [
    "summary",
    "issuetype",
    "priority",
    "status",
    "assignee",
    "reporter",
    "created",
    "updated",
    "resolutiondate",
    "labels",
    "components",
]


class IssueLoader:
    """Download issues via Enhanced JQL Search + bulkfetch."""

    def __init__(self, client: JiraClient) -> None:
        self._client = client

    def load(
        self,
        jql: str,
        *,
        extra_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Download all issues for the given JQL query.

        Strategy:
          1. JQL search for issue IDs/keys (up to 5000 per page, cheap)
          2. Bulkfetch issue details in batches of 100
        """
        logger.info("Searching issues with JQL: %s", jql)

        id_results = self._client.paginate_jql_search(
            jql,
            fields=["id", "key"],
            max_results=5000,
        )

        issue_keys = [item["key"] for item in id_results if "key" in item]
        logger.info("Found %d issue keys", len(issue_keys))

        if not issue_keys:
            return []

        fields = list(DEFAULT_ISSUE_FIELDS)
        if extra_fields:
            for field in extra_fields:
                if field not in fields:
                    fields.append(field)

        all_issues: list[dict[str, Any]] = []

        batches = [
            issue_keys[i : i + BULK_FETCH_BATCH_SIZE]
            for i in range(0, len(issue_keys), BULK_FETCH_BATCH_SIZE)
        ]

        for batch in tqdm(batches, desc="Downloading issues", unit="batch"):
            issues = self._client.bulk_fetch_issues(batch, fields=fields)
            all_issues.extend(issues)

        logger.info("Downloaded %d issues", len(all_issues))
        return all_issues

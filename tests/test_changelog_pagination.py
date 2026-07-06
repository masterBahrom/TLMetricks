"""Tests for bulk changelog pagination and missing-key reporting."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from jira_analytics.jira.client import JiraClient
from jira_analytics.loader.changelog_loader import (
    ChangelogLoader,
    missing_requested_keys,
    returned_issue_keys,
)


def _issue_change_log(issue_id: str, history_count: int = 1) -> dict:
    return {
        "issueId": issue_id,
        "changeHistories": [{"id": str(i), "items": []} for i in range(history_count)],
    }


class TestBulkFetchChangelogsPagination:
    def _client_with_responses(self, responses: list) -> JiraClient:
        client = JiraClient("https://example.atlassian.net", "user@example.com", "token")
        client.post = MagicMock(side_effect=responses)  # type: ignore[method-assign]
        return client

    def test_paginates_using_next_page_token(self) -> None:
        client = self._client_with_responses(
            [
                {
                    "issueChangeLogs": [_issue_change_log("1", 2), _issue_change_log("2", 1)],
                    "nextPageToken": "page-2",
                },
                {
                    "issueChangeLogs": [_issue_change_log("3", 1)],
                    "nextPageToken": None,
                },
            ]
        )

        result = client.bulk_fetch_changelogs(["TL-1", "TL-2", "TL-3"])

        assert len(result) == 3
        assert client.post.call_count == 2

    def test_is_last_absent_does_not_stop_pagination(self) -> None:
        client = self._client_with_responses(
            [
                {
                    "issueChangeLogs": [_issue_change_log("1")],
                    "nextPageToken": "more",
                },
                {
                    "issueChangeLogs": [_issue_change_log("2")],
                },
            ]
        )

        result = client.bulk_fetch_changelogs(["TL-1", "TL-2"])

        assert len(result) == 2
        assert client.post.call_count == 2

    def test_multiple_pages_merged(self) -> None:
        client = self._client_with_responses(
            [
                {"issueChangeLogs": [_issue_change_log("10"), _issue_change_log("11")], "nextPageToken": "t2"},
                {"issueChangeLogs": [_issue_change_log("12")], "nextPageToken": "t3"},
                {"issueChangeLogs": [_issue_change_log("13")], "nextPageToken": None},
            ]
        )

        result = client.bulk_fetch_changelogs(["A", "B", "C", "D"])

        assert [entry["issueId"] for entry in result] == ["10", "11", "12", "13"]

    def test_next_page_token_sent_in_second_request(self) -> None:
        client = self._client_with_responses(
            [
                {"issueChangeLogs": [_issue_change_log("1")], "nextPageToken": "cursor-abc"},
                {"issueChangeLogs": [_issue_change_log("2")]},
            ]
        )

        client.bulk_fetch_changelogs(["TL-1", "TL-2"])

        second_body = client.post.call_args_list[1].kwargs["json"]
        assert second_body["nextPageToken"] == "cursor-abc"
        assert second_body["issueIdsOrKeys"] == ["TL-1", "TL-2"]

    def test_no_infinite_loop_on_repeated_token(self) -> None:
        client = self._client_with_responses(
            [
                {"issueChangeLogs": [_issue_change_log("1")], "nextPageToken": "same"},
                {"issueChangeLogs": [_issue_change_log("2")], "nextPageToken": "same"},
            ]
        )

        result = client.bulk_fetch_changelogs(["TL-1"])

        assert len(result) == 2
        assert client.post.call_count == 2

    def test_logs_each_page(self, caplog: pytest.LogCaptureFixture) -> None:
        client = self._client_with_responses(
            [
                {"issueChangeLogs": [_issue_change_log("1", 3)], "nextPageToken": "p2"},
                {"issueChangeLogs": [_issue_change_log("2", 1)]},
            ]
        )

        with caplog.at_level(logging.INFO):
            client.bulk_fetch_changelogs(["TL-1"])

        messages = [record.message for record in caplog.records]
        assert any("Bulk changelog page 1" in message and "has_nextPageToken=True" in message for message in messages)
        assert any("Bulk changelog page 2" in message and "has_nextPageToken=False" in message for message in messages)


class TestChangelogLoaderMissingKeys:
    def test_missing_requested_keys_reported(self) -> None:
        entries = [
            {"issueId": "100", "changeHistories": [{}]},
            {"issueKey": "TL-2", "histories": [{}]},
        ]
        key_to_id = {"TL-1": "100", "TL-2": "200", "TL-3": "300"}

        missing = missing_requested_keys(["TL-1", "TL-2", "TL-3"], entries, key_to_id)

        assert missing == ["TL-3"]

    def test_returned_issue_keys_resolves_issue_id(self) -> None:
        entries = [{"issueId": "28694", "changeHistories": []}]
        keys = returned_issue_keys(entries, {"TL-50": "28694"})
        assert keys == {"TL-50"}

    def test_loader_logs_missing_and_optional_fallback(self, caplog: pytest.LogCaptureFixture) -> None:
        client = MagicMock()
        client.bulk_fetch_changelogs.return_value = [
            {"issueId": "1", "changeHistories": [{"id": "1", "items": []}]},
        ]
        client.get_issue_changelog.return_value = [{"id": "9", "items": []}]

        loader = ChangelogLoader(client, enable_per_issue_fallback=True)
        key_to_id = {"TL-1": "1", "TL-2": "2"}

        with caplog.at_level(logging.WARNING):
            entries = loader.load(["TL-1", "TL-2"], key_to_id=key_to_id)

        assert any("missing 1/2" in record.message for record in caplog.records)
        client.get_issue_changelog.assert_called_once_with("TL-2")
        assert len(entries) == 2
        assert entries[-1]["issueKey"] == "TL-2"

    def test_loader_skips_fallback_when_disabled(self) -> None:
        client = MagicMock()
        client.bulk_fetch_changelogs.return_value = [
            {"issueId": "1", "changeHistories": [{"id": "1", "items": []}]},
        ]

        loader = ChangelogLoader(client, enable_per_issue_fallback=False)
        entries = loader.load(["TL-1", "TL-2"], key_to_id={"TL-1": "1", "TL-2": "2"})

        assert len(entries) == 1
        client.get_issue_changelog.assert_not_called()

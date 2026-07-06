"""Tests for bulk changelog issueId → issueKey indexing."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from jira_analytics.parser.timeline_builder import TimelineBuilder, index_changelog_by_issue
from jira_analytics.validators.timeline_data_quality import assess_timeline_data_quality

from tests.conftest import REFERENCE, history, make_issue, make_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "cache"


def _bulk_record(issue_id: str, histories: list[dict]) -> dict:
    return {"issueId": issue_id, "changeHistories": histories}


def _per_issue_record(issue_key: str, histories: list[dict]) -> dict:
    return {"issueKey": issue_key, "histories": histories}


class TestIndexChangelogByIssue:
    def test_bulk_issue_id_maps_to_issue_key(self) -> None:
        histories = [history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress")]
        changelog = [_bulk_record("28694", histories)]
        id_to_key = {"28694": "TL-50"}

        indexed = index_changelog_by_issue(changelog, id_to_key)

        assert "TL-50" in indexed
        assert len(indexed["TL-50"]) == 1

    def test_per_issue_format_still_works(self) -> None:
        histories = [history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress")]
        changelog = [_per_issue_record("TL-1", histories)]

        indexed = index_changelog_by_issue(changelog, {})

        assert indexed["TL-1"] == histories

    def test_mixed_bulk_and_per_issue_formats(self) -> None:
        h1 = [history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress")]
        h2 = [history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "9", "Done")]
        changelog = [
            _bulk_record("100", h1),
            _per_issue_record("TL-2", h2),
        ]
        id_to_key = {"100": "TL-1"}

        indexed = index_changelog_by_issue(changelog, id_to_key)

        assert len(indexed["TL-1"]) == 1
        assert len(indexed["TL-2"]) == 1

    def test_unmapped_issue_id_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        changelog = [_bulk_record("99999", [])]

        with caplog.at_level(logging.WARNING):
            indexed = index_changelog_by_issue(changelog, {})

        assert indexed == {}
        assert any("Unmapped changelog record" in record.message for record in caplog.records)
        assert any("99999" in record.message for record in caplog.records)


class TestTL50LikeTimeline:
    def test_bulk_changelog_produces_multiple_periods(self) -> None:
        if not (CACHE_DIR / "changelog.json").exists():
            pytest.skip("cache not found")

        issues_raw = json.loads((CACHE_DIR / "issues.json").read_text())
        changelog = json.loads((CACHE_DIR / "changelog.json").read_text())
        issues = issues_raw if isinstance(issues_raw, list) else issues_raw.get("issues", issues_raw)
        issue = next(i for i in issues if i["key"] == "TL-50")

        builder = TimelineBuilder(make_registry(), reference_time=REFERENCE)
        document = builder.build_all(issues, changelog)
        timeline = document.timelines["TL-50"]

        assert len(timeline.periods) > 1
        assert not any("No status transitions found" in w for w in timeline.warnings)
        status_names = [period.status_name for period in timeline.periods]
        assert "In Progress" in status_names
        assert "Done" in status_names

    def test_data_quality_improves_for_tl50(self) -> None:
        if not (CACHE_DIR / "changelog.json").exists():
            pytest.skip("cache not found")

        issues_raw = json.loads((CACHE_DIR / "issues.json").read_text())
        changelog = json.loads((CACHE_DIR / "changelog.json").read_text())
        issues = issues_raw if isinstance(issues_raw, list) else issues_raw.get("issues", issues_raw)
        id_to_key = {str(i["id"]): i["key"] for i in issues if i.get("id") and i.get("key")}

        builder = TimelineBuilder(make_registry(), reference_time=REFERENCE)
        changelog_by_key = index_changelog_by_issue(changelog, id_to_key)
        document = builder.build_all(issues, changelog)
        quality = assess_timeline_data_quality(issues, changelog_by_key, document)

        assert quality.issues_with_changelog >= 28
        assert "TL-50" in changelog_by_key
        assert quality.issues_with_status_transitions >= 1

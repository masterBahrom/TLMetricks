"""Tests for IssueMetadataEnricher."""

from __future__ import annotations

import json
from pathlib import Path

from jira_analytics.metrics.calculator import MetricCalculator
from jira_analytics.metrics.enricher import IssueMetadataEnricher, extract_issue_metadata
from jira_analytics.parser.timeline_builder import TimelineBuilder

from tests.conftest import REFERENCE, history, make_issue, make_registry, make_workflow

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "cache"


class TestExtractIssueMetadata:
    def test_maps_jira_fields(self) -> None:
        raw = json.loads((FIXTURE_DIR / "issues.json").read_text())[0]
        meta = extract_issue_metadata(raw, project_key="TL")

        assert meta["summary"] == "Sample completed issue"
        assert meta["assignee"] == "Alex Engineer"
        assert meta["reporter"] == "Pat Product"
        assert meta["issue_type"] == "Task"
        assert meta["priority"] == "Medium"
        assert meta["story_points"] == 5.0
        assert meta["sprint"] == "Sprint 1"
        assert meta["labels"] == ["backend"]
        assert meta["components"] == ["API"]
        assert meta["resolution"] == "Done"
        assert meta["project_key"] == "TL"


class TestIssueMetadataEnricher:
    def test_enriches_calculated_metrics(self) -> None:
        issue = make_issue(
            "TL-123",
            created="2025-01-01T09:00:00.000+0000",
            status_id="5",
            status_name="Done",
            resolution="2025-01-05T17:00:00.000+0000",
            summary="Enriched summary",
            assignee="Dev One",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "1", "To Do", "2", "In Progress"),
            history("2", "2025-01-04T10:00:00.000+0000", "2", "In Progress", "5", "Done"),
        ]
        timeline = TimelineBuilder(make_registry(), reference_time=REFERENCE).build_issue_timeline(
            issue, histories
        )
        metrics = MetricCalculator(make_workflow()).calculate(timeline)
        assert metrics.summary is None

        metadata = {
            "project_key": "TL",
            "story_points_field": {"id": "customfield_10030"},
            "sprint_field": {"id": "customfield_10020"},
        }
        enriched = IssueMetadataEnricher([issue], metadata, project_key="TL").enrich(metrics)

        assert enriched.summary == "Enriched summary"
        assert enriched.assignee == "Dev One"
        assert enriched.issue_type == "Task"
        assert enriched.lead_time_seconds == metrics.lead_time_seconds
        assert enriched.flow_efficiency_percent is not None

    def test_flow_efficiency_on_calculator(self) -> None:
        issue = make_issue(
            "TL-200",
            created="2025-01-01T09:00:00.000+0000",
            status_id="5",
            status_name="Done",
            resolution="2025-01-05T17:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "1", "To Do", "2", "In Progress"),
            history("2", "2025-01-04T10:00:00.000+0000", "2", "In Progress", "5", "Done"),
        ]
        timeline = TimelineBuilder(make_registry(), reference_time=REFERENCE).build_issue_timeline(
            issue, histories
        )
        metrics = MetricCalculator(make_workflow()).calculate(timeline)
        assert metrics.flow_efficiency_percent is not None
        assert metrics.flow_efficiency_percent <= 100.0

"""Regression tests for buffer_time_hours across the metrics pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jira_analytics.metrics.calculator import MetricCalculator
from jira_analytics.models.metrics import METRICS_SCHEMA_VERSION, IssueMetrics, MetricsDocument
from jira_analytics.parser.timeline_builder import TimelineBuilder

from tests.conftest import REFERENCE, history, make_issue, make_registry, make_workflow

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "cache"


class TestIssueMetricsModel:
    def test_buffer_time_hours_is_first_class_field(self) -> None:
        assert "buffer_time_hours" in IssueMetrics.model_fields
        assert "buffer_time_seconds" in IssueMetrics.model_fields


class TestMetricCalculator:
    def test_assigns_buffer_time_hours(self) -> None:
        issue = make_issue(
            "TL-123",
            created="2025-01-01T09:00:00.000+0000",
            status_id="9",
            status_name="Done",
            resolution="2025-01-05T17:00:00.000+0000",
        )
        histories = [
            history("1", "2025-01-01T10:00:00.000+0000", "2", "To Do", "3", "In Progress"),
            history("2", "2025-01-02T10:00:00.000+0000", "3", "In Progress", "4", "Review"),
            history("3", "2025-01-03T10:00:00.000+0000", "4", "Review", "6", "QA IN PROGRESS"),
            history("4", "2025-01-04T10:00:00.000+0000", "6", "QA IN PROGRESS", "9", "Done"),
        ]
        timeline = TimelineBuilder(make_registry(), reference_time=REFERENCE).build_issue_timeline(
            issue, histories
        )
        metrics = MetricCalculator(make_workflow()).calculate(timeline)

        assert metrics.buffer_time_seconds == 3600
        assert metrics.buffer_time_hours == 1.0


class TestMetricsJson:
    def test_completed_issues_export_buffer_time_hours(self) -> None:
        if not (CACHE_DIR / "metrics.json").exists():
            pytest.skip("cache not found")

        raw = json.loads((CACHE_DIR / "metrics.json").read_text())
        assert raw.get("schema_version") == METRICS_SCHEMA_VERSION

        done = [issue for issue in raw["issues"] if issue.get("is_done")]
        assert done, "expected completed issues in cache"
        assert all("buffer_time_hours" in issue for issue in done)

        doc = MetricsDocument.model_validate(raw)
        tl50 = next((issue for issue in doc.issues if issue.issue_key == "TL-50"), None)
        if tl50 is not None:
            assert tl50.buffer_time_hours > 0


class TestDashboardLoader:
    def test_loader_exposes_buffer_time_hours(self) -> None:
        if not (CACHE_DIR / "metrics.json").exists():
            pytest.skip("cache not found")

        from dashboard.loader import clear_loader_cache, load_dashboard_data

        clear_loader_cache()
        data = load_dashboard_data(str(CACHE_DIR))
        done = [issue for issue in data.issues if issue.is_done]
        assert done
        assert all(hasattr(issue, "buffer_time_hours") for issue in done)

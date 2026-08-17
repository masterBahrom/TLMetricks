"""End-to-end dashboard smoke tests against live cache."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard import charts
from dashboard.filters import FilterState, apply_filters
from dashboard.insights import generate_insights
from dashboard.loader import clear_loader_cache, load_dashboard_data
from dashboard.tables import (
    aging_table,
    explorer_table,
    issues_to_dataframe,
    lead_time_table,
    reopened_table,
    status_analysis_table,
    throughput_dataframe,
)
from jira_analytics.models.metrics import METRICS_SCHEMA_VERSION, IssueMetrics

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "cache"

DASHBOARD_PAGES = [
    "Executive Dashboard",
    "Lead Time",
    "Throughput",
    "Flow Analysis",
    "Buffer Analysis",
    "Blocked Analysis",
    "Bug Analysis",
    "Aging",
    "Status Analysis",
    "Bottlenecks",
    "Reopened Issues",
    "Issue Explorer",
    "Issue Metric Inspector",
    "Management Insights",
]

CHART_PAGES = {
    "Lead Time",
    "Throughput",
    "Flow Analysis",
    "Buffer Analysis",
    "Blocked Analysis",
    "Bug Analysis",
    "Aging",
    "Status Analysis",
    "Bottlenecks",
    "Reopened Issues",
}

SCHEMA_V21_FIELDS = (
    "buffer_time_hours",
    "buffer_time_seconds",
    "blocked_time_hours",
    "blocked_time_seconds",
    "terminal_blocked_time_hours",
    "terminal_blocked_time_seconds",
    "net_cycle_time_hours",
    "net_cycle_time_seconds",
    "net_flow_efficiency_percent",
    "terminal_time_hours",
    "terminal_time_seconds",
    "status_periods",
    "flow_efficiency_percent",
    "total_active_time_hours",
    "waiting_time_hours",
)


@pytest.fixture(autouse=True)
def _clear_loader_cache() -> None:
    clear_loader_cache()
    yield
    clear_loader_cache()


@pytest.fixture(scope="module")
def dashboard_data():
    if not (CACHE_DIR / "metrics.json").exists():
        pytest.skip("cache not found")
    return load_dashboard_data(str(CACHE_DIR))


class TestSchemaCompatibility:
    def test_metrics_schema_version(self) -> None:
        if not (CACHE_DIR / "metrics.json").exists():
            pytest.skip("cache not found")

        raw = json.loads((CACHE_DIR / "metrics.json").read_text())
        assert raw["schema_version"] == METRICS_SCHEMA_VERSION

    def test_issue_metrics_exposes_v21_fields(self) -> None:
        for field in SCHEMA_V21_FIELDS:
            assert field in IssueMetrics.model_fields

    def test_completed_issues_have_buffer_time_hours(self, dashboard_data) -> None:
        done = [issue for issue in dashboard_data.issues if issue.is_done]
        assert done
        assert all(hasattr(issue, "buffer_time_hours") for issue in done)


class TestDataLayer:
    def test_tables_build_with_real_data(self, dashboard_data) -> None:
        filters = FilterState()
        issues = apply_filters(dashboard_data, filters)

        assert len(issues_to_dataframe(dashboard_data.issues, dashboard_data.flow_by_key)) == len(
            dashboard_data.issues
        )
        assert not lead_time_table(issues).empty
        assert not status_analysis_table(dashboard_data).empty
        assert not aging_table(dashboard_data).empty
        assert not explorer_table(dashboard_data, filters, "").empty
        assert not reopened_table(issues).empty
        assert not throughput_dataframe(dashboard_data, "weekly").empty

    def test_charts_have_data_points(self, dashboard_data) -> None:
        lead = [issue.lead_time_hours for issue in dashboard_data.issues if issue.lead_time_hours]
        buffer = [
            issue.buffer_time_hours
            for issue in dashboard_data.issues
            if issue.is_done and issue.buffer_time_hours > 0
        ]
        assert lead
        assert buffer
        assert len(charts.histogram(lead, "Lead Time").data[0].x) > 0
        assert len(charts.histogram(buffer, "Buffer Time").data[0].x) > 0

    def test_insights_generate(self, dashboard_data) -> None:
        insights = generate_insights(dashboard_data)
        assert insights
        assert all(isinstance(item, str) for item in insights)


class TestDownloads:
    def test_export_payloads_are_non_empty(self, dashboard_data) -> None:
        metrics_bytes = (dashboard_data.cache_dir / "metrics.json").read_bytes()
        analytics_bytes = (dashboard_data.cache_dir / "analytics.json").read_bytes()
        csv_bytes = (
            issues_to_dataframe(dashboard_data.issues, dashboard_data.flow_by_key)
            .to_csv(index=False)
            .encode("utf-8")
        )

        assert len(metrics_bytes) > 1_000
        assert len(analytics_bytes) > 1_000
        assert len(csv_bytes) > 1_000


class TestPageSmoke:
    @pytest.mark.parametrize("page_name", DASHBOARD_PAGES)
    def test_page_renders_without_exception(self, page_name: str) -> None:
        if not (CACHE_DIR / "metrics.json").exists():
            pytest.skip("cache not found")

        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(REPO_ROOT / "dashboard" / "app.py"), default_timeout=60)
        at.run()
        assert not at.exception, f"App failed to start: {at.exception}"

        if page_name != "Executive Dashboard":
            at.sidebar.radio[1].set_value(page_name).run()

        assert not at.exception, f"{page_name} raised: {at.exception}"
        assert not at.error, f"{page_name} showed errors: {[e.value for e in at.error]}"
        assert at.title, f"{page_name} missing title"
        assert at.title[0].value == page_name

        has_content = bool(
            at.metric or at.dataframe or at.get("plotly_chart") or at.markdown or at.info
        )
        assert has_content, f"{page_name} rendered no widgets"

        if page_name in CHART_PAGES:
            assert at.get("plotly_chart"), f"{page_name} expected plotly charts"

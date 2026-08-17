"""Tests for Phase 6 Streamlit dashboard."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from dashboard.filters import FilterState, apply_filters, available_statuses
from dashboard.insights import generate_insights
from dashboard.loader import clear_loader_cache, load_dashboard_data
from dashboard.tables import explorer_table, issues_to_dataframe, status_analysis_table, throughput_dataframe

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "cache"


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_loader_cache()
    yield
    clear_loader_cache()


@pytest.fixture(scope="module")
def dashboard_data():
    if not (CACHE_DIR / "metrics.json").exists():
        pytest.skip("cache not found")
    return load_dashboard_data(str(CACHE_DIR))


class TestRouting:
    def test_no_streamlit_pages_directory(self) -> None:
        """Streamlit auto-discovers pages/ next to app.py — causes blank multipage routes."""
        assert not (REPO_ROOT / "dashboard" / "pages").exists()
        assert (REPO_ROOT / "dashboard" / "views").exists()

    def test_all_views_expose_render(self) -> None:
        from dashboard.views import (
            aging,
            blocked_analysis,
            bottlenecks,
            buffer_analysis,
            bug_analysis,
            executive,
            explorer,
            flow,
            inspector,
            lead_time,
            management,
            reopened,
            status,
            throughput,
        )

        for module in [
            executive,
            lead_time,
            throughput,
            flow,
            buffer_analysis,
            blocked_analysis,
            bug_analysis,
            aging,
            status,
            bottlenecks,
            reopened,
            explorer,
            inspector,
            management,
        ]:
            assert callable(getattr(module, "render", None))

    def test_dashboard_starts_import(self) -> None:
        import dashboard.app  # noqa: F401

    def test_loads_cache(self, dashboard_data) -> None:
        assert dashboard_data.project_key == dashboard_data.analytics.project_key
        assert dashboard_data.metrics.issues
        assert dashboard_data.load_time_seconds < 2.0

    def test_required_files_only(self, dashboard_data) -> None:
        assert (dashboard_data.cache_dir / "metrics.json").exists()
        assert (dashboard_data.cache_dir / "analytics.json").exists()
        assert (dashboard_data.cache_dir / "timelines.json").exists()
        assert (dashboard_data.cache_dir / "workflow_analysis.yaml").exists()


class TestAppRender:
    def test_all_pages_render_content(self) -> None:
        if not (CACHE_DIR / "metrics.json").exists():
            pytest.skip("cache not found")

        from streamlit.testing.v1 import AppTest

        app_path = REPO_ROOT / "dashboard" / "app.py"
        pages = [
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

        at = AppTest.from_file(str(app_path), default_timeout=30)
        at.run()
        assert not at.exception

        nav = at.sidebar.radio[1]
        for page in pages:
            if page != "Executive Dashboard":
                nav.set_value(page).run()
            assert not at.exception, f"{page} raised: {at.exception}"
            assert at.title, f"{page} missing title"
            assert at.title[0].value == page
            has_content = bool(
                at.metric or at.dataframe or at.get("plotly_chart") or at.markdown or at.info
            )
            assert has_content, f"{page} rendered no widgets"


class TestFilters:
    def test_filters_subset_issues(self, dashboard_data) -> None:
        all_issues = dashboard_data.issues
        filtered = apply_filters(dashboard_data, FilterState(statuses=["Done"]))
        assert len(filtered) <= len(all_issues)
        assert all(issue.current_status == "Done" for issue in filtered)

    def test_open_only_filter(self, dashboard_data) -> None:
        filtered = apply_filters(dashboard_data, FilterState(open_only=True))
        assert all(not issue.is_done for issue in filtered)

    def test_available_statuses(self, dashboard_data) -> None:
        statuses = available_statuses(dashboard_data)
        assert statuses


class TestAnalyticsAlignment:
    def test_totals_equal_analytics(self, dashboard_data) -> None:
        summary = dashboard_data.analytics.summary
        assert dashboard_data.metrics.project.total_issues == summary.total_issues
        assert dashboard_data.metrics.project.done_count == summary.completed_issues
        assert dashboard_data.metrics.project.open_count == summary.open_issues
        assert dashboard_data.metrics.project.throughput == summary.total_throughput

    def test_flow_efficiency_matches(self, dashboard_data) -> None:
        summary = dashboard_data.analytics.summary
        flow = dashboard_data.analytics.flow
        assert summary.average_flow_efficiency_percent == flow.average_efficiency_percent


class TestTables:
    def test_explorer_dataframe_columns(self, dashboard_data) -> None:
        df = explorer_table(dashboard_data, FilterState(), "")
        expected = {
            "Issue",
            "Summary",
            "Status",
            "Assignee",
            "Priority",
            "Lead Time (h)",
            "Cycle Time (h)",
            "Net Cycle Time (h)",
            "Waiting (h)",
            "Blocked Time (h)",
            "Flow Efficiency (%)",
            "Net Flow Efficiency (%)",
            "Reopened",
            "Story Points",
        }
        assert expected.issubset(set(df.columns))

    def test_status_analysis_not_empty(self, dashboard_data) -> None:
        df = status_analysis_table(dashboard_data)
        assert not df.empty


class TestInsights:
    def test_insights_generated(self, dashboard_data) -> None:
        insights = generate_insights(dashboard_data)
        assert insights
        assert all(isinstance(item, str) for item in insights)


class TestCharts:
    def test_charts_build(self, dashboard_data) -> None:
        from dashboard import charts

        lead = [issue.lead_time_hours for issue in dashboard_data.issues if issue.lead_time_hours]
        assert charts.histogram(lead, "Lead Time").data
        assert charts.box_plot(lead, "Lead Time").data

        df = throughput_dataframe(dashboard_data, "weekly")
        if not df.empty:
            assert charts.bar_chart(df["Period"].tolist(), df["Count"].tolist(), "Weekly").data


class TestPerformance:
    def test_load_20k_issues_under_two_seconds(self, tmp_path) -> None:
        if not (CACHE_DIR / "analytics.json").exists():
            pytest.skip("cache not found")

        base_metrics = json.loads((CACHE_DIR / "metrics.json").read_text())
        issue_template = base_metrics["issues"][0]
        issues = []
        for idx in range(20_000):
            issue = dict(issue_template)
            issue["issue_key"] = f"TL-{idx}"
            issue["issue_id"] = str(10_000 + idx)
            issues.append(issue)
        base_metrics["issues"] = issues
        base_metrics["project"]["total_issues"] = 20_000

        (tmp_path / "metrics.json").write_text(json.dumps(base_metrics))
        (tmp_path / "analytics.json").write_text((CACHE_DIR / "analytics.json").read_text())
        (tmp_path / "timelines.json").write_text((CACHE_DIR / "timelines.json").read_text())
        (tmp_path / "workflow_analysis.yaml").write_text(
            (CACHE_DIR / "workflow_analysis.yaml").read_text()
        )

        clear_loader_cache()
        started = time.perf_counter()
        data = load_dashboard_data(str(tmp_path))
        df = issues_to_dataframe(data.issues, data.flow_by_key)
        elapsed = time.perf_counter() - started

        assert len(df) == 20_000
        assert elapsed < 2.0, f"Load + dataframe took {elapsed:.2f}s"

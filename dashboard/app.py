"""Jira Analytics — interactive Streamlit dashboard (Phase 6)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import DASHBOARD_VERSION
from dashboard.filters import FilterState, render_filters
from dashboard.loader import load_dashboard_data
from dashboard.tables import issues_to_dataframe
from dashboard.views import (
    aging,
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

logger = logging.getLogger(__name__)

PAGES: dict[str, object] = {
    "Executive Dashboard": executive.render,
    "Lead Time": lead_time.render,
    "Throughput": throughput.render,
    "Flow Analysis": flow.render,
    "Buffer Analysis": buffer_analysis.render,
    "Bug Analysis": bug_analysis.render,
    "Aging": aging.render,
    "Status Analysis": status.render,
    "Bottlenecks": bottlenecks.render,
    "Reopened Issues": reopened.render,
    "Issue Explorer": explorer.render,
    "Issue Metric Inspector": inspector.render,
    "Management Insights": management.render,
}


def _log_loaded_data(data) -> None:
    """Debug logging for cache load verification."""
    analytics = data.analytics
    lines = [
        f"Loaded metrics: {len(data.metrics.issues)} issues (project {data.project_key})",
        f"Loaded analytics: summary total_issues={analytics.summary.total_issues}",
        f"Loaded throughput: daily={len(analytics.throughput.daily)} weekly={len(analytics.throughput.weekly)} monthly={len(analytics.throughput.monthly)}",
        f"Loaded bottlenecks: queue={analytics.bottlenecks.largest_queue is not None}",
        f"Loaded aging: open={analytics.aging.open_issue_count} oldest={len(analytics.aging.top_oldest)}",
        f"Loaded flow: per_issue={len(analytics.flow.per_issue)} avg={analytics.flow.average_efficiency_percent}",
        f"Loaded reopen: percent={analytics.summary.reopen_percent}",
        f"Loaded explorer: {len(data.issues)} issues in metrics",
    ]
    for line in lines:
        logger.info(line)


def _render_exports(data) -> None:
    st.sidebar.divider()
    st.sidebar.header("Export")

    report = data.report_path()
    if report and report.exists():
        st.sidebar.download_button(
            "Excel Report",
            report.read_bytes(),
            file_name=report.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.sidebar.caption("Excel report not found. Run python run_report.py")

    metrics_path = data.cache_dir / "metrics.json"
    analytics_path = data.cache_dir / "analytics.json"
    st.sidebar.download_button(
        "metrics.json",
        metrics_path.read_bytes(),
        file_name="metrics.json",
        mime="application/json",
    )
    st.sidebar.download_button(
        "analytics.json",
        analytics_path.read_bytes(),
        file_name="analytics.json",
        mime="application/json",
    )

    csv = issues_to_dataframe(data.issues, data.flow_by_key).to_csv(index=False).encode("utf-8")
    st.sidebar.download_button(
        "All Issues CSV",
        csv,
        file_name=f"{data.project_key}_all_issues.csv",
        mime="text/csv",
    )


def _validate_data(data) -> bool:
    """Return False and show UI warning if core data is missing."""
    ok = True
    if not data.metrics.issues:
        st.error("No metrics data loaded. Run python run_metrics.py.")
        ok = False
    if data.analytics.summary.total_issues == 0:
        st.warning("Analytics summary reports zero issues.")
    if not data.analytics.throughput.weekly and not data.analytics.throughput.daily:
        st.info("No throughput timeline in analytics.json.")
    return ok


def _render_page(page_name: str, data, filters: FilterState) -> None:
    render_fn = PAGES[page_name]
    try:
        render_fn(data, filters)
    except Exception as exc:
        logger.exception("Page render failed: %s", page_name)
        st.error(f"Failed to render {page_name}.")
        st.exception(exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    st.set_page_config(
        page_title="Jira Analytics Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    try:
        cache_dir = str(ROOT / "cache")
        data = load_dashboard_data(cache_dir)
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        logger.exception("Failed to load dashboard data")
        st.error("Failed to load analytics data.")
        st.exception(exc)
        st.stop()

    _log_loaded_data(data)

    st.sidebar.title("Jira Analytics")
    st.sidebar.caption(f"v{DASHBOARD_VERSION} · loaded in {data.load_time_seconds:.3f}s")

    filters = render_filters(data)
    page_name = st.sidebar.radio("Navigate", list(PAGES.keys()), key="dashboard_page")
    _render_exports(data)

    if not _validate_data(data):
        st.stop()

    _render_page(page_name, data, filters)


if __name__ == "__main__":
    main()

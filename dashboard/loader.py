"""Load cache files once and keep in memory."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import yaml

from jira_analytics.analytics.models import AnalyticsDocument
from jira_analytics.config.loader import PROJECT_ROOT, load_cache_config
from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import IssueMetrics, MetricsDocument

REQUIRED_CACHE_FILES = ("metrics.json", "analytics.json", "workflow_analysis.yaml")


@dataclass(frozen=True)
class DashboardData:
    """In-memory snapshot of cache inputs for the dashboard."""

    metrics: MetricsDocument
    analytics: AnalyticsDocument
    workflow: WorkflowConfig
    cache_dir: Path
    load_time_seconds: float

    @property
    def project_key(self) -> str:
        return self.analytics.project_key

    @property
    def issues(self) -> list[IssueMetrics]:
        return self.metrics.issues

    @property
    def flow_by_key(self) -> dict[str, float]:
        result = {
            issue.issue_key: issue.flow_efficiency_percent
            for issue in self.metrics.issues
            if issue.flow_efficiency_percent is not None
        }
        if result:
            return result
        return {
            entry.issue_key: entry.efficiency_percent
            for entry in self.analytics.flow.per_issue
        }

    def report_path(self) -> Path | None:
        reports_dir = PROJECT_ROOT / "reports"
        if not reports_dir.exists():
            return None
        candidates = sorted(reports_dir.glob("Jira_Analytics_Report_*.xlsx"), reverse=True)
        return candidates[0] if candidates else None


def _resolve_cache_dir(cache_dir: Path | None) -> Path:
    if cache_dir is not None:
        return Path(cache_dir)
    config = load_cache_config()
    return PROJECT_ROOT / config.cache_dir


@lru_cache(maxsize=1)
def load_dashboard_data(cache_dir: str | None = None) -> DashboardData:
    """Load metrics, analytics, and workflow from cache (cached in-process)."""
    started = perf_counter()
    directory = _resolve_cache_dir(Path(cache_dir) if cache_dir else None)

    missing = [name for name in REQUIRED_CACHE_FILES if not (directory / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing cache files: {', '.join(missing)}. "
            "Run Phases 3–4 first (python run_metrics.py && python run_analytics.py)."
        )

    metrics = MetricsDocument.model_validate_json((directory / "metrics.json").read_text())
    analytics = AnalyticsDocument.model_validate_json((directory / "analytics.json").read_text())
    workflow_data = yaml.safe_load((directory / "workflow_analysis.yaml").read_text()) or {}
    workflow = WorkflowConfig.model_validate(workflow_data)

    return DashboardData(
        metrics=metrics,
        analytics=analytics,
        workflow=workflow,
        cache_dir=directory,
        load_time_seconds=perf_counter() - started,
    )


def clear_loader_cache() -> None:
    """Clear in-process loader cache (for tests)."""
    load_dashboard_data.cache_clear()

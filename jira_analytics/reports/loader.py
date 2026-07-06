"""Load report inputs from cache (metrics, analytics, workflow only)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from jira_analytics.analytics.models import AnalyticsDocument
from jira_analytics.config.workflow import WorkflowConfig
from jira_analytics.models.metrics import MetricsDocument


REPORT_VERSION = "5.0.0"
REQUIRED_CACHE_FILES = ("metrics.json", "analytics.json", "workflow_analysis.yaml")


@dataclass(frozen=True)
class ReportInputs:
    """Validated inputs for Excel report generation."""

    metrics: MetricsDocument
    analytics: AnalyticsDocument
    workflow: WorkflowConfig
    cache_dir: Path


def load_report_inputs(cache_dir: Path) -> ReportInputs:
    """Load metrics, analytics, and workflow config from cache."""
    cache_dir = Path(cache_dir)
    missing = [name for name in REQUIRED_CACHE_FILES if not (cache_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing cache files: {', '.join(missing)}. "
            "Run Phases 3–4 first (python run_metrics.py && python run_analytics.py)."
        )

    metrics = MetricsDocument.model_validate_json((cache_dir / "metrics.json").read_text())
    analytics = AnalyticsDocument.model_validate_json((cache_dir / "analytics.json").read_text())

    workflow_path = cache_dir / "workflow_analysis.yaml"
    workflow_data = yaml.safe_load(workflow_path.read_text()) or {}
    workflow = WorkflowConfig.model_validate(workflow_data)

    return ReportInputs(
        metrics=metrics,
        analytics=analytics,
        workflow=workflow,
        cache_dir=cache_dir,
    )

"""Phase 4 CLI — build analytics from cached metrics and timelines."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from jira_analytics.analytics import AnalyticsEngine, AnalyticsValidator
from jira_analytics.cache import CacheStore
from jira_analytics.config import load_cache_config, load_workflow_config
from jira_analytics.config.loader import ConfigError, DEFAULT_WORKFLOW_PATH
from jira_analytics.models.metrics import MetricsDocument
from jira_analytics.models.timeline import TimelinesDocument
from jira_analytics.utils import setup_logging

logger = logging.getLogger(__name__)

REQUIRED_FILES = ("metrics.json", "timelines.json")


def main() -> int:
    """Compute advanced analytics — no Jira API calls."""
    setup_logging()
    logger.info("Jira Analytics — Phase 4 Analytics Engine")

    try:
        config = load_cache_config()
        workflow = load_workflow_config()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    cache = CacheStore(config.cache_dir)
    missing = [name for name in REQUIRED_FILES if not cache.exists(name)]
    if missing:
        logger.error(
            "Missing cache files: %s. Run Phase 3 first (python run_metrics.py).",
            ", ".join(missing),
        )
        return 1

    try:
        metrics = MetricsDocument.model_validate(cache.load_metrics())
        timelines = TimelinesDocument.model_validate(cache.load_timelines())
    except FileNotFoundError as exc:
        logger.error("Cache read error: %s", exc)
        return 1

    # Snapshot workflow config into cache for reproducibility
    workflow_cache_path = cache.cache_dir / "workflow_analysis.yaml"
    shutil.copy2(DEFAULT_WORKFLOW_PATH, workflow_cache_path)

    print(f"Project: {metrics.project.project_key}")
    print(f"Issues: {metrics.project.total_issues} ({metrics.project.done_count} done, {metrics.project.open_count} open)")

    engine = AnalyticsEngine(workflow, reference_time=metrics.generated_at)
    document = engine.run(metrics, timelines)

    report = AnalyticsValidator().validate(document, metrics)
    cache.save_analytics(document)

    print(f"Throughput: {document.summary.total_throughput}")
    if document.flow.average_efficiency_percent is not None:
        print(f"Flow Efficiency: {document.flow.average_efficiency_percent:.1f}%")
    print(f"Reopen rate: {document.summary.reopen_percent:.1f}%")
    print(f"Aging (open): {document.aging.open_issue_count} issues")
    print(f"Validation: {report.error_count} errors, {report.warning_count} warnings")

    if report.issues:
        print("\nValidation report:")
        for item in report.issues[:10]:
            prefix = "ERROR" if item.severity == "error" else "WARN"
            print(f"  [{prefix}] {item.code}: {item.message}")

    print(f"\nCache saved to: {config.cache_dir.resolve()}/analytics.json")

    return 1 if not report.is_valid else 0


if __name__ == "__main__":
    sys.exit(main())

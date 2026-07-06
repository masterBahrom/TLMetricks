"""Phase 3 CLI — compute metrics from cached timelines."""

from __future__ import annotations

import logging
import sys

from jira_analytics.config import load_cache_config, load_workflow_config
from jira_analytics.config.loader import ConfigError
from jira_analytics.metrics import IssueMetadataEnricher, MetricCalculator, MetricsExporter, ProjectAggregator
from jira_analytics.models.metrics import MetricsDocument
from jira_analytics.models.timeline import TimelinesDocument
from jira_analytics.utils import setup_logging
from jira_analytics.utils.datetime_utils import parse_jira_datetime
from jira_analytics.validators.metrics_validator import MetricsValidator

logger = logging.getLogger(__name__)

REQUIRED_FILES = ("timelines.json", "status_registry.json", "metadata.json", "issues.json")


def main() -> int:
    """Compute engineering metrics from Phase 2 timelines — no Jira API calls."""
    setup_logging()
    logger.info("Jira Analytics — Phase 3 Metrics Engine")

    try:
        config = load_cache_config()
        workflow = load_workflow_config()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    exporter = MetricsExporter(config.cache_dir)
    missing = [name for name in REQUIRED_FILES if not exporter._store.exists(name)]
    if missing:
        logger.error(
            "Missing Phase 2 cache files: %s. Run Phase 2 first (python run_timelines.py).",
            ", ".join(missing),
        )
        return 1

    try:
        timelines_raw = exporter._store.load_timelines()
        metadata = exporter.load_metadata()
        raw_issues = exporter._store.load_issues()
    except FileNotFoundError as exc:
        logger.error("Cache read error: %s", exc)
        return 1

    timelines_doc = TimelinesDocument.model_validate(timelines_raw)
    project_key = metadata.get("project_key", config.project_key or "unknown")

    print(f"Project: {project_key}")
    print(f"Terminal statuses: {', '.join(workflow.terminal_statuses[:5])}{'...' if len(workflow.terminal_statuses) > 5 else ''}")
    print(f"Loading {len(timelines_doc.timelines)} timelines from cache")

    calculator = MetricCalculator(workflow)
    issue_metrics = calculator.calculate_all(timelines_doc.timelines)

    enricher = IssueMetadataEnricher(raw_issues, metadata, project_key=project_key, workflow=workflow)
    issue_metrics = enricher.enrich_all(issue_metrics)
    if enricher.missing_issue_count:
        print(f"Warning: {enricher.missing_issue_count} issue(s) missing from issues.json")

    aggregator = ProjectAggregator()
    project_metrics, bug_analytics = aggregator.aggregate(project_key, issue_metrics, workflow=workflow)

    manifest = exporter._store.load_manifest() if exporter._store.exists("manifest.json") else {}
    source_issues_at = parse_jira_datetime(manifest.get("sync_date"))

    document = MetricsDocument.from_parts(
        project_metrics,
        issue_metrics,
        source_timelines_at=timelines_doc.generated_at,
        source_issues_at=source_issues_at,
        bug_analytics=bug_analytics,
    )

    report = MetricsValidator().validate_document(document)
    exporter.export(document)

    print(f"Issues computed: {len(issue_metrics)}")
    print(f"Done: {project_metrics.done_count} | Open: {project_metrics.open_count} | Reopened: {project_metrics.reopened_count}")
    if project_metrics.median_lead_time_seconds is not None:
        print(f"Median Lead Time: {project_metrics.median_lead_time_seconds / 3600:.1f} hours")
    if project_metrics.median_cycle_time_seconds is not None:
        print(f"Median Cycle Time: {project_metrics.median_cycle_time_seconds / 3600:.1f} hours")
    if project_metrics.median_buffer_time_seconds is not None:
        print(f"Median Buffer Time: {project_metrics.median_buffer_time_seconds / 3600:.1f} hours")
    if project_metrics.bug_rate_percent is not None:
        print(f"Bug Rate: {project_metrics.bug_rate_percent:.1f}%")
    print(f"Validation: {report.error_count} errors, {report.warning_count} warnings")

    if report.issues:
        print("\nValidation report:")
        for item in report.issues[:15]:
            prefix = "ERROR" if item.severity == "error" else "WARN"
            label = item.issue_key if item.issue_key != "PROJECT" else "project"
            print(f"  [{prefix}] {label}: {item.message}")
        if len(report.issues) > 15:
            print(f"  ... and {len(report.issues) - 15} more")

    print(f"\nCache saved to: {config.cache_dir.resolve()}/metrics.json")

    return 1 if not report.is_valid else 0


if __name__ == "__main__":
    sys.exit(main())

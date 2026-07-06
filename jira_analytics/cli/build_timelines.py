"""Phase 2 CLI — build timelines from cached Phase 1 data."""

from __future__ import annotations

import logging
import sys

from jira_analytics.cache import CacheStore
from jira_analytics.config import load_cache_config
from jira_analytics.config.loader import ConfigError
from jira_analytics.parser.status_registry import build_status_registry
from jira_analytics.parser.timeline_builder import TimelineBuilder
from jira_analytics.utils import setup_logging
from jira_analytics.validators import TimelineValidator

logger = logging.getLogger(__name__)

REQUIRED_CACHE_FILES = ("metadata.json", "issues.json", "changelog.json", "manifest.json")


def main() -> int:
    """Build timelines from Phase 1 cache — no Jira API calls."""
    setup_logging()
    logger.info("Jira Analytics — Phase 2 Timeline Builder")

    try:
        config = load_cache_config()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    cache = CacheStore(config.cache_dir)

    missing = [name for name in REQUIRED_CACHE_FILES if not cache.exists(name)]
    if missing:
        logger.error(
            "Missing Phase 1 cache files: %s. Run Phase 1 sync first (python run.py).",
            ", ".join(missing),
        )
        return 1

    try:
        metadata = cache.load_metadata()
        issues = cache.load_issues()
        changelog = cache.load_changelog()
        manifest = cache.load_manifest()
    except FileNotFoundError as exc:
        logger.error("Cache read error: %s", exc)
        return 1

    print(f"Project: {manifest.get('project', config.project_key or 'unknown')}")
    print(f"Loading {len(issues)} issues from cache")

    registry = build_status_registry(metadata)
    cache.save_status_registry(registry)

    builder = TimelineBuilder(registry)
    document = builder.build_all(issues, changelog)

    validator = TimelineValidator(reference_time=document.generated_at)
    report = validator.validate_document(document)
    document.validation_warnings = [
        f"[{item.issue_key}] {item.code}: {item.message}"
        for item in report.issues
        if item.severity == "warning"
    ]

    cache.save_timelines(document)

    print(f"Status registry: {len(registry.statuses)} statuses")
    print(f"Timelines built: {document.issue_count} issues")
    print(f"Validation: {report.error_count} errors, {report.warning_count} warnings")

    if report.issues:
        print("\nValidation report:")
        for item in report.issues[:20]:
            prefix = "ERROR" if item.severity == "error" else "WARN"
            print(f"  [{prefix}] {item.issue_key}: {item.message}")
        if len(report.issues) > 20:
            print(f"  ... and {len(report.issues) - 20} more")

    print(f"\nCache saved to: {config.cache_dir.resolve()}")
    print("  status_registry.json")
    print("  timelines.json")

    return 1 if not report.is_valid else 0


if __name__ == "__main__":
    sys.exit(main())

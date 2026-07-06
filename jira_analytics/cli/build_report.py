"""Phase 5 CLI — build Excel report from cached metrics and analytics."""

from __future__ import annotations

import logging
import sys
import time
from datetime import date
from pathlib import Path

from jira_analytics.config import load_cache_config
from jira_analytics.config.loader import ConfigError
from jira_analytics.reports.excel_builder import ExcelReportBuilder, SHEET_NAMES
from jira_analytics.reports.loader import load_report_inputs
from jira_analytics.utils import setup_logging

logger = logging.getLogger(__name__)


def report_filename(for_date: date | None = None) -> str:
    d = for_date or date.today()
    return f"Jira_Analytics_Report_{d.year}_{d.month:02d}_{d.day:02d}.xlsx"


def main() -> int:
    """Generate Excel report — no Jira API calls, no recalculation."""
    setup_logging()
    logger.info("Jira Analytics — Phase 5 Excel Report")

    try:
        config = load_cache_config()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    cache_dir = Path(config.cache_dir)
    output_dir = Path(__file__).resolve().parents[2] / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        inputs = load_report_inputs(cache_dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    output_path = output_dir / report_filename(inputs.analytics.generated_at.date())

    print(f"Project: {inputs.analytics.project_key}")
    print(f"Issues: {inputs.analytics.summary.total_issues}")
    print(f"Building report: {output_path.name}")

    started = time.perf_counter()
    ExcelReportBuilder(inputs).build(output_path)
    elapsed = time.perf_counter() - started

    print(f"Sheets: {len(SHEET_NAMES)}")
    print(f"Saved to: {output_path.resolve()}")
    print(f"Completed in {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

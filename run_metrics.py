#!/usr/bin/env python3
"""Convenience entry point from repository root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jira_analytics.cli.build_metrics import main

if __name__ == "__main__":
    raise SystemExit(main())

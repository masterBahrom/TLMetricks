#!/usr/bin/env python3
"""Entry point: python jira_analytics/run.py"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path when run directly
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from jira_analytics.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())

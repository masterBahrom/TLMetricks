#!/usr/bin/env python3
"""Entry point: python run_metrics.py"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from jira_analytics.cli.build_metrics import main

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Launch the Jira Analytics Streamlit dashboard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    app_path = Path(__file__).resolve().parent / "dashboard" / "app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

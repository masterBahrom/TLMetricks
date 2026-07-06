"""Manual Jira pipeline refresh triggered from the Streamlit dashboard."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CREDENTIALS_ERROR = (
    "Jira credentials are missing. Add JIRA_EMAIL and JIRA_API_TOKEN to Streamlit secrets."
)

PIPELINE_STEPS: tuple[tuple[str, str, int], ...] = (
    ("Sync Jira", "run.py", 15 * 60),
    ("Build timelines", "run_timelines.py", 5 * 60),
    ("Build metrics", "run_metrics.py", 5 * 60),
    ("Build analytics", "run_analytics.py", 5 * 60),
    ("Generate report", "run_report.py", 5 * 60),
)


@dataclass(frozen=True)
class StepResult:
    """Outcome of a single pipeline subprocess."""

    label: str
    script: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class PipelineResult:
    """Outcome of the full refresh pipeline."""

    success: bool
    steps: tuple[StepResult, ...]
    failed_step: str | None = None
    error_message: str | None = None

    @property
    def stderr(self) -> str:
        if not self.steps:
            return self.error_message or ""
        failed = next((step for step in self.steps if not step.ok), None)
        return failed.stderr if failed else ""


def _secrets_credentials() -> dict[str, str]:
    """Read Jira credentials from Streamlit secrets when available."""
    try:
        import streamlit as st
    except ImportError:
        return {}

    try:
        secrets = st.secrets
    except Exception:
        return {}

    values: dict[str, str] = {}
    for key in ("JIRA_EMAIL", "JIRA_API_TOKEN"):
        try:
            value = secrets.get(key)  # type: ignore[attr-defined]
        except Exception:
            value = None
        if value:
            values[key] = str(value)
    return values


def resolve_jira_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build subprocess environment including Jira credentials."""
    env = dict(base_env or os.environ)
    for key, value in _secrets_credentials().items():
        env.setdefault(key, value)
    return env


def check_credentials(env: dict[str, str] | None = None) -> tuple[bool, str | None]:
    """Return whether Jira credentials are available for Phase 1 sync."""
    merged = resolve_jira_env(env)
    if merged.get("JIRA_EMAIL") and merged.get("JIRA_API_TOKEN"):
        return True, None
    return False, CREDENTIALS_ERROR


def run_step(
    project_root: Path,
    label: str,
    script_name: str,
    *,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> StepResult:
    """Run one pipeline script via subprocess."""
    script_path = project_root / script_name
    command = [sys.executable, str(script_path)]
    completed = subprocess.run(
        command,
        cwd=project_root,
        env=resolve_jira_env(env),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return StepResult(
        label=label,
        script=script_name,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def run_pipeline(
    project_root: Path,
    *,
    env: dict[str, str] | None = None,
    on_step_start: Callable[[str, str], None] | None = None,
    on_step_complete: Callable[[StepResult], None] | None = None,
) -> PipelineResult:
    """
    Run the full Jira analytics pipeline sequentially.

    Stops on the first failed step without modifying cache on failure.
    """
    ok, error = check_credentials(env)
    if not ok:
        return PipelineResult(success=False, steps=(), failed_step=None, error_message=error)

    steps: list[StepResult] = []
    for label, script_name, timeout_seconds in PIPELINE_STEPS:
        if on_step_start:
            on_step_start(label, script_name)
        result = run_step(
            project_root,
            label,
            script_name,
            timeout_seconds=timeout_seconds,
            env=env,
        )
        steps.append(result)
        if on_step_complete:
            on_step_complete(result)
        if not result.ok:
            return PipelineResult(
                success=False,
                steps=tuple(steps),
                failed_step=label,
                error_message=result.stderr.strip() or f"{script_name} exited with {result.returncode}",
            )

    return PipelineResult(success=True, steps=tuple(steps))

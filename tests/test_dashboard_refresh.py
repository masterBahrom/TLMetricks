"""Tests for manual dashboard data refresh."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dashboard.loader import clear_loader_cache, load_dashboard_data
from dashboard.refresh import (
    CREDENTIALS_ERROR,
    PIPELINE_STEPS,
    PipelineResult,
    StepResult,
    check_credentials,
    resolve_jira_env,
    run_pipeline,
    run_step,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "cache"


@pytest.fixture(autouse=True)
def _clear_loader() -> None:
    clear_loader_cache()
    yield
    clear_loader_cache()


class TestCheckCredentials:
    def test_missing_credentials_returns_error(self) -> None:
        ok, error = check_credentials({"PATH": "/usr/bin"})
        assert not ok
        assert error == CREDENTIALS_ERROR

    def test_present_credentials_returns_ok(self) -> None:
        env = {"JIRA_EMAIL": "user@example.com", "JIRA_API_TOKEN": "secret"}
        ok, error = check_credentials(env)
        assert ok
        assert error is None


class TestRunStep:
    @patch("dashboard.refresh.subprocess.run")
    def test_run_step_invokes_subprocess(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        result = run_step(
            REPO_ROOT,
            "Sync Jira",
            "run.py",
            timeout_seconds=60,
            env={"JIRA_EMAIL": "a@b.com", "JIRA_API_TOKEN": "tok"},
        )
        assert result.ok
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert kwargs["cwd"] == REPO_ROOT
        assert kwargs["timeout"] == 60
        assert kwargs["env"]["JIRA_EMAIL"] == "a@b.com"


class TestRunPipeline:
    @patch("dashboard.refresh.run_step")
    def test_successful_pipeline_runs_steps_in_order(self, mock_run_step: MagicMock) -> None:
        mock_run_step.side_effect = [
            StepResult(label=label, script=script, returncode=0, stdout="", stderr="")
            for label, script, _ in PIPELINE_STEPS
        ]
        env = {"JIRA_EMAIL": "user@example.com", "JIRA_API_TOKEN": "secret"}
        result = run_pipeline(REPO_ROOT, env=env)

        assert result.success
        assert len(result.steps) == len(PIPELINE_STEPS)
        called_scripts = [call.args[2] for call in mock_run_step.call_args_list]
        assert called_scripts == [script for _, script, _ in PIPELINE_STEPS]

    @patch("dashboard.refresh.run_step")
    def test_failed_step_stops_pipeline(self, mock_run_step: MagicMock) -> None:
        mock_run_step.side_effect = [
            StepResult(label="Sync Jira", script="run.py", returncode=0, stdout="", stderr=""),
            StepResult(
                label="Build timelines",
                script="run_timelines.py",
                returncode=1,
                stdout="",
                stderr="timeline error",
            ),
        ]
        env = {"JIRA_EMAIL": "user@example.com", "JIRA_API_TOKEN": "secret"}
        result = run_pipeline(REPO_ROOT, env=env)

        assert not result.success
        assert result.failed_step == "Build timelines"
        assert "timeline error" in result.stderr
        assert mock_run_step.call_count == 2

    def test_missing_credentials_skips_subprocess(self) -> None:
        with patch("dashboard.refresh.run_step") as mock_run_step:
            result = run_pipeline(REPO_ROOT, env={"PATH": "/usr/bin"})
        assert not result.success
        assert result.error_message == CREDENTIALS_ERROR
        mock_run_step.assert_not_called()

    @patch("dashboard.refresh.run_step")
    def test_successful_pipeline_does_not_modify_cache_files(
        self, mock_run_step: MagicMock, tmp_path: Path
    ) -> None:
        if not (CACHE_DIR / "metrics.json").exists():
            pytest.skip("cache not found")

        metrics_path = tmp_path / "metrics.json"
        analytics_path = tmp_path / "analytics.json"
        workflow_path = tmp_path / "workflow_analysis.yaml"
        for src, dst in [
            (CACHE_DIR / "metrics.json", metrics_path),
            (CACHE_DIR / "analytics.json", analytics_path),
            (CACHE_DIR / "workflow_analysis.yaml", workflow_path),
        ]:
            dst.write_text(src.read_text())

        original_metrics = json.loads(metrics_path.read_text())
        mock_run_step.return_value = StepResult(
            label="Sync Jira",
            script="run.py",
            returncode=1,
            stdout="",
            stderr="sync failed",
        )
        env = {"JIRA_EMAIL": "user@example.com", "JIRA_API_TOKEN": "secret"}
        result = run_pipeline(REPO_ROOT, env=env)

        assert not result.success
        assert json.loads(metrics_path.read_text()) == original_metrics


class TestResolveJiraEnv:
    def test_secrets_fill_missing_env(self) -> None:
        with patch("dashboard.refresh._secrets_credentials", return_value={"JIRA_EMAIL": "s@x.com"}):
            env = resolve_jira_env({"JIRA_API_TOKEN": "tok"})
        assert env["JIRA_EMAIL"] == "s@x.com"
        assert env["JIRA_API_TOKEN"] == "tok"


class TestAppGetDataButton:
    def test_get_data_button_exists_in_sidebar(self) -> None:
        if not (CACHE_DIR / "metrics.json").exists():
            pytest.skip("cache not found")

        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(REPO_ROOT / "dashboard" / "app.py"), default_timeout=30)
        at.run()
        assert not at.exception
        assert at.sidebar.button
        labels = [btn.label for btn in at.sidebar.button]
        assert "Get Data" in labels

    @patch("dashboard.app.run_pipeline")
    @patch("dashboard.app.check_credentials")
    def test_missing_credentials_shows_error(
        self,
        mock_check: MagicMock,
        mock_pipeline: MagicMock,
    ) -> None:
        if not (CACHE_DIR / "metrics.json").exists():
            pytest.skip("cache not found")

        from streamlit.testing.v1 import AppTest

        mock_check.return_value = (False, CREDENTIALS_ERROR)
        at = AppTest.from_file(str(REPO_ROOT / "dashboard" / "app.py"), default_timeout=30)
        at.run()
        get_data = next(btn for btn in at.sidebar.button if btn.label == "Get Data")
        get_data.click().run()
        assert not at.exception
        mock_pipeline.assert_not_called()
        errors = [e.value for e in at.sidebar.error]
        assert any(CREDENTIALS_ERROR in e for e in errors)

class TestRenderGetData:
    @patch("dashboard.app.load_dashboard_data")
    @patch("dashboard.app.clear_loader_cache")
    @patch("dashboard.app.run_pipeline")
    @patch("dashboard.app.check_credentials")
    @patch("dashboard.app.st")
    def test_successful_refresh_clears_cache_and_returns_rerun(
        self,
        mock_st: MagicMock,
        mock_check: MagicMock,
        mock_pipeline: MagicMock,
        mock_clear: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from dashboard.app import _render_get_data

        mock_st.session_state = {}
        mock_st.sidebar.button.return_value = True
        mock_check.return_value = (True, None)
        mock_pipeline.return_value = PipelineResult(success=True, steps=())
        status_cm = MagicMock()
        mock_st.sidebar.status.return_value.__enter__ = MagicMock(return_value=status_cm)
        mock_st.sidebar.status.return_value.__exit__ = MagicMock(return_value=False)

        assert _render_get_data("cache") is True

        mock_check.assert_called_once()
        mock_pipeline.assert_called_once()
        mock_clear.assert_called_once()
        mock_load.assert_called_once_with("cache")
        assert mock_st.session_state["_refresh_success"] is True

    @patch("dashboard.app.run_pipeline")
    @patch("dashboard.app.check_credentials")
    @patch("dashboard.app.st")
    def test_failed_refresh_keeps_data_and_shows_error(
        self,
        mock_st: MagicMock,
        mock_check: MagicMock,
        mock_pipeline: MagicMock,
    ) -> None:
        from dashboard.app import _render_get_data

        mock_st.session_state = {}
        mock_st.sidebar.button.return_value = True
        mock_check.return_value = (True, None)
        mock_pipeline.return_value = PipelineResult(
            success=False,
            steps=(
                StepResult(
                    label="Sync Jira",
                    script="run.py",
                    returncode=1,
                    stdout="",
                    stderr="sync failed",
                ),
            ),
            failed_step="Sync Jira",
            error_message="sync failed",
        )
        status_cm = MagicMock()
        mock_st.sidebar.status.return_value.__enter__ = MagicMock(return_value=status_cm)
        mock_st.sidebar.status.return_value.__exit__ = MagicMock(return_value=False)

        assert _render_get_data("cache") is False
        mock_st.sidebar.error.assert_called()
        mock_st.sidebar.code.assert_called_with("sync failed")

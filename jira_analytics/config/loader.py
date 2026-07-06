"""Load and validate configuration from YAML and environment variables."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from jira_analytics.config.models import AppConfig, CacheConfig
from jira_analytics.config.workflow import WorkflowConfig

DEFAULT_CONFIG_PATH = Path(__file__).parent / "settings.yaml"
DEFAULT_WORKFLOW_PATH = Path(__file__).parent / "workflow_analysis.yaml"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


def load_config(config_path: Path | None = None) -> AppConfig:
    """
    Load configuration from YAML file and environment variables.

    Credentials (email, api_token) MUST come from environment variables:
      - JIRA_EMAIL
      - JIRA_API_TOKEN

    YAML supplies jira_url, project_key, jql, and cache_dir.
    Environment variables override YAML values where applicable.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv()

    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    with path.open(encoding="utf-8") as handle:
        raw: dict = yaml.safe_load(handle) or {}

    email = os.getenv("JIRA_EMAIL") or raw.get("email")
    api_token = os.getenv("JIRA_API_TOKEN") or raw.get("api_token")

    if not email:
        raise ConfigError(
            "Missing JIRA_EMAIL environment variable. "
            "Set it in .env or export JIRA_EMAIL=your.email@example.com"
        )
    if not api_token:
        raise ConfigError(
            "Missing JIRA_API_TOKEN environment variable. "
            "Set it in .env or export JIRA_API_TOKEN=your_token"
        )

    merged = {
        "jira_url": os.getenv("JIRA_URL") or raw.get("jira_url"),
        "email": email,
        "api_token": api_token,
        "project_key": os.getenv("JIRA_PROJECT_KEY") or raw.get("project_key"),
        "jql": os.getenv("JIRA_JQL") or raw.get("jql"),
        "cache_dir": os.getenv("JIRA_CACHE_DIR") or raw.get("cache_dir", "cache"),
    }

    missing = [key for key in ("jira_url", "project_key", "jql") if not merged.get(key)]
    if missing:
        raise ConfigError(f"Missing required configuration keys: {', '.join(missing)}")

    try:
        return AppConfig(**merged)
    except Exception as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc


def load_cache_config(config_path: Path | None = None) -> CacheConfig:
    """
    Load minimal configuration for offline cache processing.

    Does not require Jira credentials — used by Phase 2 timeline builder.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv()

    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    with path.open(encoding="utf-8") as handle:
        raw: dict = yaml.safe_load(handle) or {}

    return CacheConfig(
        cache_dir=os.getenv("JIRA_CACHE_DIR") or raw.get("cache_dir", "cache"),
        project_key=os.getenv("JIRA_PROJECT_KEY") or raw.get("project_key"),
    )


def load_workflow_config(workflow_path: Path | None = None) -> WorkflowConfig:
    """
    Load workflow analysis configuration.

    Used by the metrics engine to classify terminal, active, and waiting statuses.
    """
    path = workflow_path or DEFAULT_WORKFLOW_PATH
    if not path.exists():
        raise ConfigError(f"Workflow configuration file not found: {path}")

    with path.open(encoding="utf-8") as handle:
        raw: dict = yaml.safe_load(handle) or {}

    try:
        return WorkflowConfig(**raw)
    except Exception as exc:
        raise ConfigError(f"Invalid workflow configuration: {exc}") from exc

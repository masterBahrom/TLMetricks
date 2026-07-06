"""Simple JSON file cache for raw Jira API data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jira_analytics.analytics.models import AnalyticsDocument
from jira_analytics.models import ProjectMetadata, SyncManifest
from jira_analytics.models.metrics import MetricsDocument
from jira_analytics.models.timeline import StatusRegistry, TimelinesDocument

logger = logging.getLogger(__name__)

METADATA_FILE = "metadata.json"
ISSUES_FILE = "issues.json"
CHANGELOG_FILE = "changelog.json"
MANIFEST_FILE = "manifest.json"
STATUS_REGISTRY_FILE = "status_registry.json"
TIMELINES_FILE = "timelines.json"
METRICS_FILE = "metrics.json"
ANALYTICS_FILE = "analytics.json"


class CacheStore:
    """Read and write cached data as JSON files."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _write_json(self, filename: str, data: Any) -> Path:
        path = self.cache_dir / filename
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, default=str)
        logger.info("Saved %s (%d bytes)", path, path.stat().st_size)
        return path

    def _read_json(self, filename: str) -> Any:
        path = self.cache_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Cache file not found: {path}")
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def save_metadata(self, metadata: ProjectMetadata) -> Path:
        """Persist discovered project metadata."""
        return self._write_json(METADATA_FILE, metadata.model_dump(mode="json"))

    def save_issues(self, issues: list[dict[str, Any]]) -> Path:
        """Persist raw issue JSON payloads."""
        return self._write_json(ISSUES_FILE, issues)

    def save_changelog(self, changelog: list[dict[str, Any]]) -> Path:
        """Persist raw changelog JSON payloads."""
        return self._write_json(CHANGELOG_FILE, changelog)

    def save_manifest(self, manifest: SyncManifest) -> Path:
        """Persist sync manifest."""
        return self._write_json(MANIFEST_FILE, manifest.model_dump(mode="json"))

    def save_status_registry(self, registry: StatusRegistry) -> Path:
        """Persist the status registry."""
        return self._write_json(STATUS_REGISTRY_FILE, registry.model_dump(mode="json"))

    def save_timelines(self, document: TimelinesDocument) -> Path:
        """Persist reconstructed issue timelines."""
        return self._write_json(TIMELINES_FILE, document.model_dump(mode="json"))

    def save_metrics(self, document: MetricsDocument) -> Path:
        """Persist computed engineering metrics."""
        return self._write_json(METRICS_FILE, document.model_dump(mode="json"))

    def save_analytics(self, document: AnalyticsDocument) -> Path:
        """Persist advanced analytics."""
        return self._write_json(ANALYTICS_FILE, document.model_dump(mode="json"))

    def load_metadata(self) -> dict[str, Any]:
        return self._read_json(METADATA_FILE)

    def load_issues(self) -> list[dict[str, Any]]:
        return self._read_json(ISSUES_FILE)

    def load_changelog(self) -> list[dict[str, Any]]:
        return self._read_json(CHANGELOG_FILE)

    def load_manifest(self) -> dict[str, Any]:
        return self._read_json(MANIFEST_FILE)

    def load_status_registry(self) -> dict[str, Any]:
        return self._read_json(STATUS_REGISTRY_FILE)

    def load_timelines(self) -> dict[str, Any]:
        return self._read_json(TIMELINES_FILE)

    def load_metrics(self) -> dict[str, Any]:
        return self._read_json(METRICS_FILE)

    def load_analytics(self) -> dict[str, Any]:
        return self._read_json(ANALYTICS_FILE)

    def exists(self, filename: str) -> bool:
        return (self.cache_dir / filename).exists()

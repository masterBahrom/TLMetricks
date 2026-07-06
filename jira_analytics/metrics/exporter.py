"""Persist metrics document to the local cache."""

from __future__ import annotations

import logging
from pathlib import Path

from jira_analytics.cache.store import CacheStore
from jira_analytics.models.metrics import MetricsDocument

logger = logging.getLogger(__name__)


class MetricsExporter:
    """Write computed metrics to cache/metrics.json."""

    def __init__(self, cache_dir: Path) -> None:
        self._store = CacheStore(cache_dir)

    def export(self, document: MetricsDocument) -> Path:
        """Serialize and persist the metrics document."""
        path = self._store.save_metrics(document)
        logger.info(
            "Exported metrics for %d issues to %s",
            len(document.issues),
            path,
        )
        return path

    def load_timelines_document(self):
        """Load timelines via cache store (typed deserialization)."""
        from jira_analytics.models.timeline import TimelinesDocument

        raw = self._store.load_timelines()
        return TimelinesDocument.model_validate(raw)

    def load_metadata(self) -> dict:
        return self._store.load_metadata()

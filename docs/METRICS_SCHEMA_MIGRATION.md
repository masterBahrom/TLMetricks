# Metrics Schema Migration (v1 → v2)

## Summary

`IssueMetrics` is now the **canonical representation** of a Jira issue. Jira metadata from Phase 1 (`issues.json`) is merged during Phase 3 metrics build. All downstream consumers read **only** `metrics.json`.

## What changed

| Area | v1 | v2 |
|------|----|----|
| `metrics.json` schema | `schema_version` absent | `schema_version: "2.0"` |
| Issue identity | `issue_key`, `issue_id` only | + `project_key`, Jira metadata fields |
| Jira fields | Not present | `summary`, `assignee`, `priority`, etc. |
| Flow efficiency | Analytics only | `flow_efficiency_percent` per issue |
| Provenance | `source_timelines_at` | + `source_issues_at` (from `manifest.json`) |
| Phase 3 input | timelines + metadata | + **issues.json** (required) |

## New `IssueMetrics` fields

```json
{
  "issue_key": "TL-123",
  "issue_id": "10001",
  "project_key": "TL",
  "summary": "Fix login bug",
  "description": null,
  "assignee": "Alex Engineer",
  "reporter": "Pat Product",
  "issue_type": "Bug",
  "priority": "High",
  "story_points": 5.0,
  "sprint": "Sprint 12",
  "labels": ["backend"],
  "components": ["API"],
  "resolution": "Done",
  "flow_efficiency_percent": 69.2308,
  "lead_time_hours": 104.0,
  "...": "existing metric fields unchanged"
}
```

## Migration steps

1. Ensure Phase 1 cache is current: `python run.py`
2. Rebuild timelines (if needed): `python run_timelines.py`
3. **Rebuild metrics** (required): `python run_metrics.py`
4. Rebuild analytics: `python run_analytics.py`
5. Regenerate report: `python run_report.py`
6. Restart dashboard: `python run_dashboard.py`

## Breaking changes

- **Old `metrics.json` files** without metadata fields will still parse (fields default to `null`/empty) but Excel/Dashboard will show `—` until metrics are rebuilt.
- **Phase 3 now requires `issues.json`**. Metrics build fails if missing.
- **Only `jira_analytics/metrics/enricher.py` reads `issues.json`**. Excel, Dashboard, and APIs must not read it directly.

## Rollback

Re-run Phase 3 with the previous code version, or delete enriched fields manually. Downstream tools tolerate missing optional fields.

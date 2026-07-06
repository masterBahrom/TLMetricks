# Jira Analytics

Production-quality Jira analytics framework for engineering metrics. Processes Jira Cloud data through a five-phase offline pipeline: acquisition → timelines → metrics → analytics → Excel report.

## Requirements

- Python 3.11+
- Jira Cloud account with API token (Phase 1 only)
- Access to the target project (default: `TL`)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Phase 1 only
```

## Pipeline

```
Phase 1: run.py           → cache/issues.json, changelog.json, metadata.json
Phase 2: run_timelines.py → cache/timelines.json, status_registry.json
Phase 3: run_metrics.py   → cache/metrics.json
Phase 4: run_analytics.py → cache/analytics.json
Phase 5: run_report.py    → reports/Jira_Analytics_Report_YYYY_MM_DD.xlsx
Phase 6: run_dashboard.py → http://localhost:8501
```

### Phase 1 — Data acquisition (Jira API)

```bash
python run.py
```

Requires `JIRA_EMAIL` and `JIRA_API_TOKEN` in `.env`.

### Phase 2 — Timeline reconstruction (offline)

```bash
python run_timelines.py
```

Reads Phase 1 cache. No Jira credentials required.

### Phase 3 — Metrics engine (offline)

```bash
python run_metrics.py
```

Reads `timelines.json`, `status_registry.json`, `metadata.json`, and **`issues.json`**. Loads `workflow_analysis.yaml`. Enriches each `IssueMetrics` with Jira metadata so `metrics.json` is self-contained. No Jira API.

### Phase 4 — Advanced analytics (offline)

```bash
python run_analytics.py
```

Reads `metrics.json`, `timelines.json`, `workflow_analysis.yaml`. Produces throughput/WIP timelines, aging, flow efficiency, queue analysis, bottlenecks, and reopen analytics.

### Phase 5 — Excel report (offline, presentation only)

```bash
python run_report.py
```

Reads **only** `cache/metrics.json`, `cache/analytics.json`, and `cache/workflow_analysis.yaml`. No Jira API, no recalculation of metrics or analytics.

Output: `reports/Jira_Analytics_Report_YYYY_MM_DD.xlsx` (openpyxl).

| Worksheet | Contents |
|-----------|----------|
| Executive Summary | KPI dashboard with conditional formatting |
| Lead Time | Per-issue lead/cycle metrics + distribution chart |
| Throughput | Daily/weekly/monthly completions + charts |
| Flow Analysis | Queue mix, bottlenecks, flow efficiency chart |
| Aging | Open issues (oldest first) + aging histogram |
| Status Analysis | Time per status + distribution chart |
| Reopened Issues | Reopened issue list |
| Raw Metrics | Full `IssueMetrics` dump |
| Configuration | Workflow status lists + metadata |
| Management Insights | Rule-based observations for executives |

**Note:** Issue summary and assignee are not in the Phase 3–4 cache contract; those columns display `—` when unavailable.

### Phase 6 — Interactive dashboard (offline, presentation only)

```bash
python run_dashboard.py
```

Open [http://localhost:8501](http://localhost:8501)

Reads **only** `cache/metrics.json`, `cache/analytics.json`, and `cache/workflow_analysis.yaml`. Streamlit + Plotly visualization layer — no recalculation, no Jira API.

| Page | Contents |
|------|----------|
| Executive Dashboard | KPI cards from analytics.json |
| Lead Time | Histogram, box plot, scatter, top 20 table |
| Throughput | Daily/weekly/monthly trends + rolling average |
| Flow Analysis | Queue mix and flow efficiency charts |
| Aging | Open issue aging buckets and histogram |
| Status Analysis | Per-status times + heatmap |
| Bottlenecks | Queue/waiting/review/QA bottlenecks |
| Reopened Issues | Reopen distribution and table |
| Issue Explorer | Searchable/sortable issue table + CSV export |
| Management Insights | Rule-based observations |

Sidebar filters apply to issue-level views; global KPIs always match `analytics.json`.

## Workflow Configuration

Metrics never rely on the literal status name `"Done"`. Configure terminal and active statuses in:

`jira_analytics/config/workflow_analysis.yaml`

| Key | Purpose |
|-----|---------|
| `terminal_statuses` | Completion, lead time, throughput |
| `cancelled_statuses` | Terminal completion for cancelled issues |
| `active_statuses` / `review_statuses` / `qa_statuses` | Cycle time, active time |
| `waiting_statuses` | Queue and blocked time |

**Reopen rule:** Only `terminal → non-terminal` transitions count as reopen.  
`Done → Post Deployment` and `Done → Released` are **not** reopens.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────┐
│  Phase 1    │     │    Phase 2       │     │    Phase 3      │     │  Phase 4+    │
│  Jira API   │ ──► │ Timeline Builder │ ──► │ Metrics Engine  │ ──► │  Dashboard   │
│  Loader     │     │                  │     │                 │     │  Reports CFD │
└─────────────┘     └──────────────────┘     └─────────────────┘     └──────────────┘
     cache/              cache/                    cache/
   issues.json        timelines.json             metrics.json
 changelog.json    status_registry.json
 metadata.json
```

### Phase 3 Metrics Engine

```
timelines.json
      ↓
MetricCalculator        (one pass per issue → IssueMetrics)
      ↓
ProjectAggregator       (percentiles, averages → ProjectMetrics)
      ↓
MetricsDocument         (project + issues + summary)
      ↓
MetricsValidator
      ↓
cache/metrics.json
```

| Component | Responsibility |
|-----------|----------------|
| `MetricCalculator` | Per-issue metrics from `IssueTimeline` (single pass) |
| `ProjectAggregator` | Percentiles, averages, throughput, status averages |
| `MetricsExporter` | Persist `MetricsDocument` to cache |
| `MetricsValidator` | Consistency checks (Lead ≥ Cycle, no NaN, etc.) |

## Cache Output

```
cache/
  metadata.json           # Phase 1: project metadata
  issues.json             # Phase 1: raw issues
  changelog.json          # Phase 1: raw changelogs
  manifest.json           # Phase 1: sync manifest
  status_registry.json    # Phase 2: status lookup
  timelines.json          # Phase 2: issue lifecycles
  metrics.json            # Phase 3: engineering metrics
  analytics.json          # Phase 4: advanced analytics
  workflow_analysis.yaml  # Phase 4: workflow snapshot
reports/
  Jira_Analytics_Report_YYYY_MM_DD.xlsx  # Phase 5
```

## Metric Definitions

### Issue Metrics (schema v2)

Each issue in `metrics.json` is the **canonical record** — Jira fields + computed metrics:

| Field | Source |
|-------|--------|
| `summary`, `assignee`, `priority`, `issue_type`, `story_points`, `sprint`, `labels`, `components` | `issues.json` (Phase 3 enricher) |
| `lead_time_*`, `cycle_time_*`, `waiting_time_*`, `flow_efficiency_percent`, `reopen_count` | Timeline calculation |
| `schema_version` | `"2.0"` |

See `docs/METRICS_SCHEMA_MIGRATION.md` for upgrade steps.

### Issue Metrics (computed)

| Metric | Definition |
|--------|------------|
| **Lead Time** | `created_date` → completion (`resolution_date` or final terminal status). Any configured terminal status completes the workflow. |
| **Cycle Time** | First active status entry → **first** terminal status entry. Post-terminal steps (e.g. Done → Post Deployment) are excluded. |
| **Total Active Time** | Sum of all periods where `status_category == indeterminate`. |
| **Waiting Time** | Sum of all non-active periods (`new`, `done`, `undefined`). |
| **Time to First Progress** | `created_date` → first `indeterminate` status entry. |
| **Time in Status** | Per-status duration aggregation (seconds, hours, days). |
| **Reopen Count** | Count of `terminal → non-terminal` transitions only. |
| **Resolution Time** | `created_date` → `resolution_date` (null for open issues). |
| **Throughput** | (Project-level) Count of completed issues. |

### Project Metrics

| Metric | Definition |
|--------|------------|
| **Average / Median / P90 Lead Time** | Computed over done issues only. |
| **Average / Median / P90 Cycle Time** | Computed over done issues with cycle time. |
| **Average Time by Status** | Mean duration per status name across all issues. |
| **Throughput** | Number of completed issues in the dataset. |

### Validation Rules

- `Lead Time ≥ Cycle Time` (for done issues)
- `Active Time + Waiting Time ≈ Lead Time` (tolerance: 2 seconds)
- Done issues must have `lead_time_seconds` and `done_date`
- Open issues must not have `resolution_time_seconds`
- No negative, NaN, or Infinity values

## Example metrics.json

```json
{
  "generated_at": "2026-07-06T07:57:44Z",
  "source_timelines_at": "2026-07-06T07:46:31Z",
  "project": {
    "project_key": "TL",
    "total_issues": 1,
    "done_count": 1,
    "open_count": 0,
    "reopened_count": 0,
    "throughput": 1,
    "median_lead_time_seconds": 374400.0,
    "median_cycle_time_seconds": 259200.0,
    "average_time_by_status": [
      {"status": "Code Review", "average_seconds": 86400.0, "average_hours": 24.0, "issue_count": 1}
    ]
  },
  "issues": [
    {
      "issue_key": "TL-123",
      "lead_time_seconds": 374400.0,
      "lead_time_hours": 104.0,
      "cycle_time_seconds": 259200.0,
      "cycle_time_hours": 72.0,
      "total_active_time_seconds": 259200.0,
      "waiting_time_seconds": 115200.0,
      "is_done": true,
      "time_in_status": [
        {"status": "To Do", "duration_seconds": 3600.0, "hours": 1.0, "days": 0.0417}
      ]
    }
  ],
  "summary": {
    "project_key": "TL",
    "total_issues": 1,
    "done_count": 1,
    "median_lead_time_hours": 104.0,
    "median_cycle_time_hours": 72.0
  }
}
```

## Project Structure

```
jira_analytics/
  config/         # YAML + pydantic config
  jira/           # HTTP client (Phase 1)
  cache/          # JSON file store
  loader/         # Data loaders (Phase 1)
  parser/         # Timeline builder (Phase 2)
  metrics/        # MetricCalculator, ProjectAggregator, MetricsExporter
  analytics/      # Phase 4 analytics engine
  reports/        # Phase 5 Excel report builder
  validators/     # Timeline + metrics validation
  cli/            # Phase 1/2/3 orchestration
  utils/          # Logging, datetime, statistics
dashboard/        # Phase 6 Streamlit dashboard (presentation)
  app.py          # Streamlit entry point
  loader.py       # Cache loader (in-memory)
  views/          # View modules (not pages/ — reserved by Streamlit)
```

## Limitations

- **Cycle Time** requires at least one active status and one terminal status; direct To Do → Done yields `cycle_time = null`.
- **Reopen detection** uses workflow config — multiple terminal statuses in sequence (Done → Released) are one completion flow.
- **Throughput** is a snapshot count of done issues, not a time-bucketed rate (future phases will add weekly/monthly throughput).
- **Percentiles** use linear interpolation over the done-issue population; small samples produce less reliable P90 values.
- **`metrics.json` v2** is self-contained — Jira metadata is enriched during Phase 3. See `docs/METRICS_SCHEMA_MIGRATION.md`.
- Future dashboards, CFD, and flow reports should consume **only** `metrics.json` — no need to re-read timelines.

## Testing

```bash
python -m pytest tests/ -v
```

## Security

Never commit `.env` or API tokens. Credentials are loaded exclusively from environment variables (Phase 1 only).

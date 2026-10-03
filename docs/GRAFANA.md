# Grafana — setup and dashboard guide

Grafana is provisioned automatically via Docker Compose with a Prometheus
data source and three dashboards loaded from version-controlled JSON files.

## Access

| | URL | Credentials |
|---|---|---|
| Grafana UI | `http://localhost:3001` | `admin` / `admin` |
| Prometheus UI | `http://localhost:9095` | (none) |

> Grafana runs on port **3001** because Langfuse already occupies 3000.

## Architecture

```
Python OTLP metrics
  → OTel Collector (4318)
    → Prometheus exporter (8888)
      → Prometheus scrape (9090)
        → Grafana data source (3001)
```

The collector's `prometheus` exporter exposes metrics at `0.0.0.0:8888`.
Prometheus scrapes this endpoint every 5 seconds. Grafana queries Prometheus.

## Provisioned files

| File | Purpose |
|---|---|
| `infrastructure/grafana/provisioning/datasources/prometheus.yml` | Auto-configures Prometheus data source |
| `infrastructure/grafana/provisioning/dashboards/dashboards.yml` | Points Grafana at the dashboards folder |
| `infrastructure/grafana/dashboards/llm_service_overview.json` | Dashboard 1 |
| `infrastructure/grafana/dashboards/llm_token_cost_analytics.json` | Dashboard 2 |
| `infrastructure/grafana/dashboards/llm_failure_slo_diagnostics.json` | Dashboard 3 |
| `infrastructure/prometheus-rules.yml` | Recording + alerting rules |

## Dashboards

### 1. LLM Service Overview

| Panel | Query | Type |
|---|---|---|
| Total Requests (1h) | `sum(increase(llm_obs_llm_requests_total[1h]))` | stat |
| Success Rate (1h) | `success / total` | stat |
| P95 Latency (1h) | `histogram_quantile(0.95, ...)` | stat |
| Error Budget Remaining (7d) | `1 - error_budget_consumed_7d` | stat |
| Request Rate by Workflow | `sum by (workflow) (rate(...))` | timeseries |
| Success vs Error Rate | `sum by (result) (rate(...))` | timeseries |
| Latency P50/P95/P99 | `histogram_quantile(...)` | timeseries |

### 2. Token and Cost Analytics

| Panel | Query | Type |
|---|---|---|
| Total Tokens (1h) | `sum(increase(llm_obs_llm_tokens_total[1h]))` | stat |
| Input Tokens (1h) | `sum(...{token_type="input"}...)` | stat |
| Output Tokens (1h) | `sum(...{token_type="output"}...)` | stat |
| Estimated Cost (1h) | `sum(increase(llm_obs_llm_estimated_cost_usd_total[1h]))` | stat |
| Tokens by Model | `sum by (model, token_type) (rate(...))` | timeseries |
| Cost by Model | `sum by (model) (rate(...))` | timeseries |
| Throughput by Workflow | `sum by (workflow) (rate(...))` | timeseries |

### 3. Failure and SLO Diagnostics

| Panel | Query | Type |
|---|---|---|
| Error Count (1h) | `sum(...{result!="success"}...)` | stat |
| Retry Attempts (1h) | `sum(...{outcome!="success"}...)` | stat |
| SLO: Success Rate (7d) | `llm_obs:success_rate_7d` | stat |
| SLO: % Under 4s (1h) | `llm_obs:pct_under_4s_1h` | stat |
| Errors by Type | `sum by (result) (rate(...))` | timeseries |
| API Attempts by Outcome | `sum by (outcome) (rate(...))` | timeseries |
| Latency Distribution | `sum by (le) (rate(..._bucket...))` | timeseries |
| Error Budget Consumption | `llm_obs:error_budget_consumed_7d` | timeseries |
| Insufficient Data Check | `llm_obs:request_total_7d` | stat |

## Alerts

Grafana-managed alerts are defined via Prometheus rules in
`infrastructure/prometheus-rules.yml`.  They are evaluated by Prometheus and
visible in Grafana's alerting UI.

| Alert | Condition | Severity |
|---|---|---|
| `LLMSuccessRateDegradation` | 7-day success rate < 99.5% | warning |
| `LLMErrorBudgetConsumption` | > 80% of error budget consumed | warning |
| `LLMLatencyBreach` | P95 latency > 4s over 1h | warning |
| `LLMInsufficientData` | < 100 samples in 7d | info |

SLO breach alerts are suppressed when insufficient data is available (the
`LLMInsufficientData` alert fires instead at `info` severity).

## Metric names

All metrics are prefixed with `llm_obs_` (from the collector's `namespace:
llm_obs` setting):

| Metric | Type | Labels |
|---|---|---|
| `llm_obs_llm_requests_total` | counter | service, model, workflow, environment, result |
| `llm_obs_llm_tokens_total` | counter | service, model, workflow, environment, token_type |
| `llm_obs_llm_estimated_cost_usd_total` | counter | service, model, workflow, environment |
| `llm_obs_llm_api_attempts_total` | counter | service, model, workflow, environment, outcome, attempt |
| `llm_obs_llm_request_duration_seconds` | histogram | service, model, workflow, environment, result |
| `llm_obs_llm_request_duration_seconds_bucket` | histogram buckets | (same + le) |

Recording rules (computed by Prometheus):

| Rule | Description |
|---|---|
| `llm_obs:request_total_7d` | Total requests in 7d |
| `llm_obs:request_success_total_7d` | Successful requests in 7d |
| `llm_obs:success_rate_7d` | 7-day success rate |
| `llm_obs:error_budget_consumed_7d` | Error budget consumed (0–1+) |
| `llm_obs:p95_latency_1h` | P95 latency over 1h |
| `llm_obs:pct_under_4s_1h` | % of requests under 4s |

## Prometheus retention

Prometheus is configured with **45-day retention**:

```yaml
--storage.tsdb.retention.time=45d
```

Data is persisted in the `prometheus_data` Docker volume.

## Populating dashboards without live API calls

Run the synthetic metrics demo:

```bash
python examples/06_synthetic_metrics.py
```

This generates 500 synthetic observations (~95% success, ~5% errors, realistic
latency/token distributions) and pushes them through the same metrics pipeline.
The data is explicitly labelled as synthetic in the script output.

## Verifying the pipeline

1. Check Prometheus targets: `http://localhost:9095/targets` — the
   `otel-collector` job should be UP.
2. Check Prometheus metrics: `http://localhost:9095/api/v1/label/__name__/values`
   — search for `llm_obs_` prefix.
3. Open Grafana: `http://localhost:3001` → dashboards should auto-appear under
   the "LLM Observability" folder.
4. Run a query in Grafana's explore panel:
   `sum(increase(llm_obs_llm_requests_total[1h]))`
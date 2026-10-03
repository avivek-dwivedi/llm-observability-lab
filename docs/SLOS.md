# SLOs — Service Level Objectives

This document defines the **internal** SLOs for the LLM observability lab and
documents a **hypothetical** monthly SLA separately.

> **Critical distinction:** An internal SLO is a team target. A provider SLA is
> a contractual obligation. This lab's SLOs are **illustrative** and must NOT
> be represented as a cloud provider's contractual SLA.

## SLO 1 — 7-day request success ≥ 99.5%

| Field | Value |
|---|---|
| **Target** | 99.5% of logical requests succeed over 7 days |
| **Window** | 7 days (rolling) |
| **Error budget** | 0.5% of requests may fail |
| **Eligible requests** | All completed logical requests (success + error) |
| **Excluded** | Requests still in-flight, retried attempts (counted separately) |

### Error budget calculation

```
allowed_errors    = total_requests × 0.005
actual_errors     = total_requests − successful_requests
budget_consumed   = actual_errors / allowed_errors
budget_remaining  = 1 − budget_consumed
```

- `budget_consumed = 0.0` → no errors, full budget remaining
- `budget_consumed = 1.0` → budget exhausted, SLO violated
- `budget_consumed > 1.0` → budget overspent

### Prometheus query

```promql
llm_obs:error_budget_consumed_7d
```

## SLO 2 — ≥ 95% under 4 seconds

| Field | Value |
|---|---|
| **Target** | ≥ 95% of **successful** logical requests complete within 4 seconds |
| **Window** | 1 hour (rolling) |
| **Threshold** | 4.0 seconds |
| **Eligible requests** | Successful logical requests only (errors excluded) |
| **Histogram bucket** | `le="4"` |

### Prometheus query

```promql
sum(rate(llm_obs_llm_request_duration_seconds_bucket{le="4"}[1h]))
/ clamp_min(sum(rate(llm_obs_llm_request_duration_seconds_count[1h])), 1)
```

## Insufficient-data state

When `total_requests < 100` (configurable via `MIN_SAMPLES`), SLO evaluations
return `insufficient_data=True` and:

- `actual`, `is_met`, `error_budget_*` are all `None`
- The Grafana "Insufficient Data Check" panel shows the sample count
- The `LLMInsufficientData` alert fires at `info` severity
- SLO breach alerts are **suppressed** (they won't fire on too few samples)

This prevents misleading percentages when the lab has only a handful of test
calls.

## Hypothetical 99% monthly SLA (documented separately)

| Field | Value |
|---|---|
| **Target** | 99.0% of requests succeed per calendar month |
| **Window** | Calendar month |
| **Error budget** | 1% of requests may fail |
| **Status** | **Hypothetical** — not computed, not enforced, not contractual |

This is a **documentation-only** target to illustrate what a monthly SLA would
look like. It is:

- NOT an internal SLO (we don't compute it in code)
- NOT a provider's contractual SLA (Groq's SLA is separate)
- NOT enforced or alerted on

If you want to compute it, use the same formula as SLO 1 with a 30-day window
and 0.99 target.

## Alerting rules

Defined in `infrastructure/prometheus-rules.yml`:

| Alert | Condition | Severity | SLO |
|---|---|---|---|
| `LLMSuccessRateDegradation` | `success_rate_7d < 0.995` | warning | SLO 1 |
| `LLMErrorBudgetConsumption` | `error_budget_consumed_7d > 0.8` | warning | SLO 1 |
| `LLMLatencyBreach` | `p95_latency_1h > 4` | warning | SLO 2 |
| `LLMInsufficientData` | `request_total_7d < 100` | info | both |

SLO breach alerts are implicitly suppressed when `LLMInsufficientData` is
firing because the recording rules return `None`-equivalent values when
sample counts are too low.
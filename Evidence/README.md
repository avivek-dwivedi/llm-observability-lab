# Evidence — Verified Run Screenshots

Screenshots captured on **2026-10-03** from the live lab, proving the full
pipeline works end-to-end:

```
Python (Groq) → OTel Collector → Langfuse / Phoenix / LangSmith
                              → Prometheus → Grafana
```

Environment: Langfuse **v3.185.0 OSS**, org `SCAI`, project
"Production AI Systems".

## Langfuse (self-hosted)

| File | What it shows |
|---|---|
| `01_langfuse_tracing.png` | **Tracing page** — 50 trace rows (`eval.*`, `batch_seq_*`, `batch_conc_*`), each with clean Input/Output text (no SDK objects leaked), latency and token columns |
| `02_langfuse_cost_dashboard.png` | **Cost Dashboard** — 35 traces / 49 observations, **$0.080685 total**, cost concentrated on `allam-2-7b`, spike at 20:30 |
| `03_langfuse_cost_top20.png` | Top-20 traces/observations by cost (~$0.004 most expensive); Users panel shows n/a (screenshot predates the `user.id` fix) |
| `04_langfuse_cost_p95.png` | **P95 cost panels** — per-trace and per-observation input/output cost percentiles |
| `05_langfuse_usage_management.png` | **Usage Management** — 40 traces / 54 observations; Score counts were 0 before the native-score fix |
| `06_langfuse_counts_by_env.png` | Trace/observation count by environment (18+24 traces, 32+23 observations) |
| `07_langfuse_latency_p95.png` | **Latency Dashboard** — P95 by use case (worst ~1.2 s) and by observation level (~750 ms) |
| `08_langfuse_latency_users_ttft.png` | Max latency by user (n/a pre-user.id fix) + TTFT-by-prompt panels (empty — non-streaming) |
| `09_langfuse_latency_by_model.png` | P95 TTFT ≈ 0 ms (non-streaming), P95 latency ~800 ms, output tokens/sec ~0 |

## Grafana (Prometheus-backed, folder "LLM Observability")

| File | Dashboard |
|---|---|
| `10_grafana_dashboard_folder.png` | Folder view — «1. Normal», «2. LLM Degraded», «3. System Failure» (tags `llm`, `sre`) |
| `11_grafana_normal.png` | **1. Normal** — 500 req, 98.8% success, 6 errors, P50 327 ms → P99 497 ms, $12.51, 91,817 tokens |
| `12_grafana_cost_token_panels.png` | Cost Over Time, Input-vs-Output tokens, API Attempts vs Successful, Errors by Type |
| `13_grafana_llm_degraded.png` | **2. LLM Degraded** — 92.2% success, P95 7.53 s, −1460% budget, $11.41, 53 failed retries |
| `14_grafana_system_failure.png` | **3. System Failure** — 52.2% success, 239 errors, −9460% budget, $6.60, 378 failed retries |

The three scenarios demonstrate SLO behaviour degrading exactly as designed:
healthy (sub-500 ms P99) → degraded model (multi-second P95, retries) →
system failure (over half of requests failing, error budget exhausted).

## Known limitations visible in the screenshots

- **Grafana cost totals include synthetic data** (the 1,500 offline
  observations from `06_synthetic_metrics.py`, priced at `$5/$15 per M`), so
  Grafana dollar figures are intentionally larger than Langfuse's
  real-trace-only totals. The two numbers measure different things by design.
- **Flat "Cost Over Time" lines** — synthetic counters jump in a single
  scrape, so `increase()`-based panels render flat. Continuous real traffic
  produces proper trends.
- **TTFT ≈ 0 ms** — scripts use non-streaming completions, so
  time-to-first-token is never recorded.
- **Users "n/a" panels** (older shots) — fixed by the `langfuse.user.id`
  attribute now stamped on all example-script traces; re-running scripts
  03/05 repopulates these panels.
- **Score counts = 0** (older shots) — fixed by `07_evaluation.py` now
  posting **native Langfuse Score objects** via the public API; re-run it
  to populate the Scores dashboards.
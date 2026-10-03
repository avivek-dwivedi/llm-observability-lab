# Evidence — Verified Run Screenshots

Screenshots captured on **2026-10-03** from the live lab, proving the full
pipeline works end-to-end:

```
Python (Groq) → OTel Collector → Langfuse / Phoenix / LangSmith
                              → Prometheus → Grafana
```

## Langfuse (self-hosted, v3.185.0 OSS)

| File | What it shows |
|---|---|
| `Screenshot 2026-10-03 203248.png` | **Tracing page** — 50 clean trace rows (`eval.*`, `batch_seq_*`, `batch_conc_*`), each with clean Input/Output text (no SDK objects leaked), latency and token columns |
| `Screenshot 2026-10-03 203302.png` | **Cost Dashboard** — 35 traces / 49 observations, $0.08 total across environments, cost concentrated on `allam-2-7b` |
| `Screenshot 2026-10-03 203327.png` | Cost dashboards — Top-20 traces/observations by cost (~$0.004 most expensive); Users panel empty pre-`user.id` fix |
| `Screenshot 2026-10-03 203333.png` | **P95 cost panels** — per-trace and per-observation input/output cost percentiles |
| `Screenshot 2026-10-03 203345.png` | **Usage Management** — 40 traces / 54 observations across 2 environments; Score counts were 0 before the native-score fix |
| `Screenshot 2026-10-03 203356.png` | Trace/observation count by environment |
| `Screenshot 2026-10-03 203410.png` | **Latency Dashboard** — P95 by use case (worst ~1.2 s) and by observation level |
| `Screenshot 2026-10-03 203418.png` | Max latency by user + TTFT panels (empty — non-streaming calls have no TTFT) |
| `Screenshot 2026-10-03 203424.png` | P95 TTFT ≈ 0 ms (non-streaming), P95 latency ~800 ms |

## Grafana (Prometheus-backed, folder "LLM Observability", three scenario dashboards)

| File | Dashboard | Requests | Success | Errors | Error budget | P50 → P99 | Cost | Tokens |
|---|---|---|---|---|---|---|---|---|
| `Screenshot 2026-10-03 203452.png` | folder view | «1. Normal», «2. LLM Degraded», «3. System Failure» (tags `llm`, `sre`) | | | | | | |
| `Screenshot 2026-10-03 203445.png` | **1. Normal** | 500 | **98.8%** | 6 | −140% | 327 ms → 497 ms | $12.51 | 91,817 |
| `Screenshot 2026-10-03 203500.png` | **2. LLM Degraded** | 500 | **92.2%** | 39 | −1460% | 3.61 s → 7.91 s | $11.41 | 84,818 |
| `Screenshot 2026-10-03 203506.png` | **3. System Failure** | 500 | **52.2%** | 239 | −9460% | 2.06 s → 3.96 s | $6.60 | 54,403 |

The three scenarios demonstrate SLO behaviour degrading exactly as designed:
healthy (sub-500 ms P99) → degraded model (multi-second P95, retries) →
system failure (over half of requests failing, error budget exhausted).

## Known limitations visible in the screenshots

- **Grafana cost totals include synthetic data** (the 1,500 offline observations
  from `06_synthetic_metrics.py` priced at `$5/$15 per M`), so Grafana dollar
  figures are intentionally larger than Langfuse's real-trace-only totals.
  The two numbers measure different things by design.
- **Flat "Cost Over Time" lines** — synthetic counters jump in a single
  scrape, so `increase()`-based panels render flat. Continuous real traffic
  produces proper trends.
- **TTFT ≈ 0 ms** — scripts use non-streaming completions, so time-to-first-token
  is never recorded.
- **Users "n/a" panels** (older shots) — fixed by the `langfuse.user.id`
  attribute added to all example scripts; re-run scripts 03/05 to populate.
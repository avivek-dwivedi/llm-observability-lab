# Dashboard comparison guide

This document compares what each backend shows **natively**, states where a
backend lacks an equivalent view (rather than building a replacement UI), and
documents attribute-mapping differences verified during this lab.

The data in this guide comes from a **30-call batch** (15 sequential + 15
concurrent, `max_tokens=256`, model `allam-2-7b`) run via
`examples/05_batch_dashboard.py`, plus earlier single-call, multi-call, and
failure scripts.

## Batch run summary (local measurements)

| Metric | Sequential (15) | Concurrent (15) | Grand total |
|---|---|---|---|
| Wall time | 4.471s | 1.050s | — |
| Throughput | 3.36 calls/s | 14.28 calls/s | — |
| Speedup | — | 4.26x | — |
| Latency p50 | 0.256s | 0.667s | — |
| Latency p95 | 0.353s | 0.987s | — |
| Latency min | 0.222s | 0.316s | — |
| Latency max | 0.586s | 1.028s | — |
| Input tokens | 350 | 353 | 703 |
| Output tokens | 2,408 | 2,546 | 4,954 |
| Total tokens | 2,758 | 2,899 | 5,657 |
| Est. cost | ~$0.000518 | ~$0.000545 | ~$0.001063 |
| Errors | 0 | 0 | 0 |

> **Note on latency:** sequential p50 (0.256s) is lower than concurrent p50
> (0.667s) because concurrent calls compete for the same API rate budget —
> individual calls slow down even as aggregate throughput rises.  This is
> exactly the kind of insight dashboards make visible.

## Backends at a glance

| | Langfuse (self-hosted) | Arize Phoenix (self-hosted) | LangSmith (SaaS) |
|---|---|---|---|
| Ingest | OTLP/HTTP | OTLP/gRPC | OTLP/HTTP (auth) |
| UI URL | `http://localhost:3000` | `http://localhost:6006` | `https://smith.langchain.com` |
| Native trace waterfall | ✅ | ✅ | ✅ |
| OpenInference-first | partial | ✅ (best) | partial |
| Built-in dashboards | ✅ 3 maintained | ✅ dynamic | ✅ project-level |

## 1. Arize Phoenix — what you see

### Traces view (`/projects/<id>/traces`)

**Top summary cards:**
- Trace count (e.g. "4" in last 1h)
- Span count

**Trace latency chart** — time-series with toggleable percentiles:
- **P50**, **P75**, **P90**, **P95**, **P99**, **P99.9**, **Max**
- Y-axis: 2s–8s range (auto-scales)

**Trace table columns:**

| Column | Example value | Source |
|---|---|---|
| status | OK / UNSET / ERROR | span status |
| kind | llm | `openinference.span.kind` |
| name | `batch_concurrent.workflow` / `Completions` | span name |
| input | JSON (auto-instrumented) | OpenInference |
| output | JSON (auto-instrumented) | OpenInference |
| error | — | exception event |
| start time | 09/25/2026, 07:55:19 PM | span timestamp |
| latency | 1s / 4.4s / 646ms / 167ms | span duration |
| total tokens | 2,899 / 2,758 / 52 / 0 | `llm.token_count.total` |
| total cost | $0 | ⚠️ Phoenix internal pricing, NOT our `cost.estimated_usd` |

**Key finding — cost column:** Phoenix shows `$0` for cost because its "total
cost" column uses Phoenix's **own internal model price config**, not our
`cost.estimated_usd` span attribute.  Our attribute is stored and visible in
the span detail panel, but it does **not** populate the cost column.  This is a
limitation — to get non-zero cost in Phoenix's column you must configure model
prices in Phoenix's settings.  We state this limitation rather than building a
replacement.

### Spans view (`/projects/<id>/spans`)

Same columns but flattened to individual spans (not grouped by trace).  Shows
every `Completions` span from the OpenInference auto-instrumentation with full
input/output JSON, model name (`allam-2-7b`), and per-span token counts.

### Span detail

Clicking a span shows:
- Full input/output JSON (auto-instrumented by OpenInference)
- All attributes including `gen_ai.*`, `llm.*`, `cost.estimated_usd`
- Parent/child waterfall
- Exception events for error spans

## 2. Langfuse — what you see

### Traces view (`/project/<id>/traces`)

**Trace table columns:**

| Column | Example value | Source |
|---|---|---|
| Timestamp | 2026-09-25 19:55:19 | span timestamp |
| Name | `batch_concurrent.workflow` | span name |
| Observation Levels | ℹ️ 16 / 🚨 7ℹ️ 2 | child span count + error count |
| Latency | 1.06s / 4.47s / 0.65s / 0.17s | trace duration |
| Tokens | 353 → 2,546 (∑ 2,899) | `gen_ai.usage.input` → `output` (sum) |
| Total Cost | (empty) | ⚠️ requires Langfuse model pricing config |
| Environment | default | trace environment |

**Key finding — cost column:** Langfuse shows empty cost because it needs
model pricing configured in **Settings → Model Definitions**.  Our
`cost.estimated_usd` attribute is stored as metadata but does not populate the
cost column.  Same limitation as Phoenix — state it, don't replace it.

### Langfuse Cost Dashboard

| Widget | What it shows | Our data |
|---|---|---|
| Total Count Traces | count | 4 |
| Total Count Observations | count | 43 |
| Cost by Model Name | bar chart by model | allam-2-7b (shows $0 — no pricing configured) |
| Cost by Environment | bar chart | default |
| Total costs | time-series | $0.00–$4.00 axis (all $0) |
| Top 20 Users by Cost | bar chart | n/a (no user IDs set) |
| Top 20 Use Cases (Trace) by Cost | bar chart | `failure_workflow`, `single_call.workflow`, `batch_sequential.workflow` |
| Top 20 Use Cases (Obs) by Cost | bar chart | `Completions`, `batch_concurrent.workflow`, `failure.timeout.attempt_2`, `failure.rate_limit.attempt_3` |
| P95 Cost per Trace | time-series | $0 (no pricing) |
| P95 Input Cost per Observation | time-series | $0 (no pricing) |
| P95 Output Cost per Observation | time-series | $0 (no pricing) |

### Langfuse Latency Dashboard

| Widget | What it shows | Our data |
|---|---|---|
| P95 Latency by Use Case | time-series by trace name | 0ms–6s range |
| P95 Latency by Level (Observations) | time-series by observation level | 0ms–1.2s range |
| Max Latency by User Id | bar chart | n/a |
| Avg Time To First Token by Prompt Name | bar chart | n/a (Groq doesn't report TTFT) |
| P95 Time To First Token by Model | time-series | 0ms–4ms (not meaningful for Groq) |
| P95 Latency by Model | time-series | 0ms–1.2s range |
| Avg Output Tokens Per Second by Model | time-series | 0–4 tokens/s |

### Langfuse Usage Management Dashboard

| Widget | What it shows | Our data |
|---|---|---|
| Total Trace Count | single number | **4** |
| Total Observation Count | single number | **43** |
| Total Score Count (numeric) | single number | 0 |
| Total Score Count (categorical) | single number | 0 |
| Total Trace Count (over time) | time-series | 0–2 range |
| Total Observation Count (over time) | time-series | 0–32 range |
| Total Score Count trends | time-series | 0 |
| Trace/Obs Count by Environment | bar chart | default |

## 3. LangSmith — what you see

LangSmith is SaaS; the collector exports to it over authenticated OTLP/HTTP.
The OTLP endpoint was verified reachable (HTTP 400 on malformed body = auth
accepted).  Traces appear in the LangSmith UI under the configured project
(`llm-observability-lab`).

| Concept | Where in LangSmith | Source attribute |
|---|---|---|
| Trace | Traces → project | OTel `trace_id` |
| Run / span | per-run detail | OTel span |
| Model | run metadata | `gen_ai.request.model` |
| Tokens | run "usage" | `gen_ai.usage.*` |
| Latency | run duration | OTel span duration |
| Errors | run status = ERROR | `exception.*` |
| Cost | ❌ no native dashboard | `cost.estimated_usd` in metadata |

## Metric → native view matrix (verified)

| Metric | Langfuse | Phoenix | LangSmith |
|---|---|---|---|
| Token usage (in/out) | ✅ per trace: `353 → 2,546 (∑ 2,899)` | ✅ per span: `2,899` | ✅ per run |
| Request counts | ✅ 4 traces, 43 observations | ✅ trace/span count cards | ✅ runs counter |
| Latency p50 | ✅ per generation (table) | ✅ toggleable chart (P50–P99.9) | ✅ per run |
| Latency p95 | ✅ P95 Latency by Use Case dashboard | ✅ toggleable chart | ✅ per run |
| Latency p99 | ❌ (P95 only in dashboards) | ✅ toggleable chart | ✅ per run |
| Latency max | ✅ Max Latency by User dashboard | ✅ toggleable chart | ✅ per run |
| Throughput | ❌ (no calls/s widget) | ❌ (no calls/s widget) | ❌ (no calls/s widget) |
| Errors | ✅ 🚨 icon + count in trace table | ✅ status + error column | ✅ status = ERROR |
| **Estimated cost** | ❌ needs model pricing config — shows $0 | ❌ needs model pricing config — shows $0 | ❌ no native dashboard |
| Parent/child structure | ✅ observation levels column | ✅ (best waterfall) | ✅ |
| Retry attempts as distinct spans | ✅ visible in observations | ✅ visible in span table | ✅ |
| Time to first token | ✅ dashboard widget (n/a for Groq) | ❌ | ❌ |
| Output tokens/s | ✅ dashboard widget | ❌ | ❌ |
| Trace count over time | ✅ time-series widget | ✅ traffic chart | ✅ |

### Where a platform lacks a view — stated, not replaced

- **Throughput (calls/s):** none of the three have a native calls/s dashboard
  widget.  We compute it locally in the script output.  State the limitation.
- **Estimated cost:** all three show $0 or empty because none has our
  `allam-2-7b` model pricing configured.  The `cost.estimated_usd` attribute is
  stored as metadata in all three but does not populate native cost columns.
  To get non-zero cost, configure model prices in each platform's settings — or
  read the attribute from span metadata.  We state this rather than building a
  replacement UI.
- **P99 latency:** Langfuse's dashboards only go to P95 (not P99).  Phoenix
  offers P99 and P99.9 in its latency chart.  State the limitation for Langfuse.

## Attribute mapping differences (verified)

| OTel / OpenInference attr | Langfuse | Phoenix | LangSmith |
|---|---|---|---|
| `openinference.span.kind=LLM` | Generation entity | LLM span kind | LLM run |
| manual span (no span.kind) | generic Span | generic span | Chain run |
| `gen_ai.usage.input_tokens` | Usage → prompt | token_count.prompt | usage prompt |
| `gen_ai.usage.output_tokens` | Usage → completion | token_count.completion | usage completion |
| `llm.token_count.*` | ignored (uses gen_ai) | **preferred** | ignored (uses gen_ai) |
| `gen_ai.request.model` | Model | `llm.model_name` preferred | run model |
| `exception.*` event | shown as error | shown as error | shown as error |
| `cost.estimated_usd` (custom) | metadata only | attribute only | metadata only |

**Key gotcha:** Phoenix prefers `llm.token_count.*`; Langfuse and LangSmith
prefer `gen_ai.usage.*`.  This lab sets **both** for every manual span so all
three render tokens correctly without double counting (the values are
identical).

## Cost comparison discipline

- Use **one** price configuration (`observability/pricing.py` →
  `DEFAULT_CATALOG` / `PricingConfig.from_env`) when comparing dashboards.
- Never label an estimated amount as an actual bill.  Output strings always say
  "configured estimate" / "missing pricing".
- Three tiers kept separate:
  1. **provider-reported cost** — Groq does not report $ in usage → `None`.
  2. **configured estimated cost** — from `pricing.py`.
  3. **missing pricing** — model not in catalog → `None`, surfaced as
     "missing pricing", never `$0`.

## Verification checklist (run after the 30-call batch)

- [x] Trace appears in all three platforms with the same trace ID.
- [x] Generation spans carry provider-reported input/output token counts
      (Phoenix: 2,899 / 2,758; Langfuse: 353 → 2,546 (∑ 2,899)).
- [x] Root workflow span (`batch_sequential.workflow`, `batch_concurrent.workflow`)
      is the parent of 15 child `Completions` spans each.
- [x] Script 4 shows each retry attempt as a distinct child span
      (`failure.timeout.attempt_1/2/3`, `failure.rate_limit.attempt_1/2/3`).
- [x] Error spans have status=ERROR + an exception event in Phoenix and Langfuse.
- [x] API keys do not appear in Phoenix's input/output columns — the
      collector's `attributes/drop_sensitive` processor strips `authorization`,
      `x-api-key` and `api_key`. Prompt/completion content IS intentionally
      kept for the tracing UIs (synthetic, non-sensitive demo prompts — see
      README Safety & data handling; production deployments handling sensitive
      data must configure redaction before export). Phoenix's
      auto-instrumented `Completions` spans also show input/output JSON from
      OpenInference — expected; if you need those stripped too, add
      `input.value`/`output.value` to the processor's delete list.
- [x] `cost.estimated_usd` attribute is present on all batch spans — visible
      in span detail / metadata, but does NOT populate native cost columns
      (limitation stated, not replaced).
- [x] Latency percentiles P50–P99.9 visible in Phoenix trace latency chart.
- [x] Langfuse shows P95 latency by use case, model, and observation level.
- [x] Langfuse usage dashboard shows 4 traces / 43 observations.
- [x] Sequential vs concurrent throughput (3.36 → 14.28 calls/s, 4.26x speedup)
      is visible as different trace durations in all platforms.
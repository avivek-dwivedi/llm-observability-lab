# Multi-Platform LLM Observability Lab

A compact, professional Python repository dedicated to **instrumenting and
observing LLM calls** made through the Groq SDK. It is **not** a chatbot,
agent, API product or LLMOps serving system — there is no frontend, chat
interface, or serving layer. The example scripts exist only to generate
controlled telemetry.

One instrumented app → one OTLP exporter → one OTel Collector → **five**
observability surfaces:

| Surface | Type | What you get |
|---|---|---|
| **Langfuse** (self-hosted) | Traces | Cost, tokens, latency, quality scores per trace |
| **Arize Phoenix** (self-hosted) | Traces | Trace waterfall with input/output JSON |
| **LangSmith** (SaaS) | Traces | Trace inspection + evaluation runs |
| **Prometheus + Grafana** | Metrics | SLOs, error budget, P50–P99, token/cost dashboards |
| **OTel Collector** | Raw | Single fan-out point for all of the above |

## What it does

### V1 — Tracing (Langfuse + Phoenix + LangSmith)

- One **OpenTelemetry TracerProvider** + **one** OTLP exporter → a local
  **OpenTelemetry Collector**.
- The collector fans the same trace out independently to the three trace
  backends above.
- Captures standard **GenAI** semantic-convention attributes plus supported
  **OpenInference** attributes.
- A `completions_span()` context manager emits clean LLM input/output
  attributes (no SDK request objects leaked into telemetry).
- Manual spans only for workflow/retry info the auto-instrumentation does
  not capture.
- Computes **estimated cost** from token counts + a configurable per-million
  price; provider-reported cost, configured estimate and missing pricing are
  three separate tiers (an estimate is never mislabeled as a bill).

### V2 — Metrics + SLOs (Prometheus + Grafana)

- **Metrics pipeline**: Python OTLP metrics → Collector → Prometheus → Grafana.
- **Counters**: completed requests, LLM tokens (input/output), estimated
  cost, API attempts.
- **Histogram**: end-to-end logical-request latency with a 4-second bucket
  boundary.
- **Two internal SLOs**: 7-day success ≥ 99.5% and ≥ 95% of requests under 4 s,
  with error-budget tracking and an insufficient-data state.
- **Three Grafana dashboards**: service overview, token/cost analytics,
  failure/SLO diagnostics — plus three scenario dashboards (Normal,
  LLM Degraded, System Failure) for demo replays.

## Repository layout

```
llm-observability/
├── observability/                # the instrumentable library
│   ├── instrumentation.py        # TracerProvider, workflow + completions spans
│   ├── metrics.py                # counters + histogram + flush
│   ├── slos.py                   # SLO evaluation + error budget
│   ├── usage.py                  # provider-reported usage extraction
│   ├── pricing.py                # estimated cost (3 tiers)
│   └── metadata.py               # GenAI + OpenInference attribute builder
├── examples/                     # telemetry-generating scripts (see table below)
├── infrastructure/
│   ├── otel-collector.yaml       # traces + metrics pipelines
│   ├── prometheus.yml            # scrape config
│   ├── prometheus-rules.yml      # SLO recording + alerting rules
│   ├── setup_langfuse_model.py   # registers Langfuse Model Definition (pricing)
│   ├── sync-keys.ps1             # .env → collector.env auth header
│   ├── import_dashboards.py      # imports demo Grafana dashboards
│   └── grafana/                  # dashboards + provisioning + datasources
├── notebooks/                    # 2 Jupyter notebooks (practical + theory)
├── docs/                         # LANGFUSE, LANGSMITH, PHOENIX, DASHBOARDS, SLOS, GRAFANA
├── tests/                        # pytest suite
├── docker-compose.yml            # Phoenix + Prometheus + Grafana + Collector
├── RUNBOOK.md                    # exact from-zero setup steps
└── .env.example
```

## Quick start

Prereqs: **Docker**, **Python ≥ 3.11**, a Groq API key, and optionally a
LangSmith API key. A Langfuse API key comes from your own self-hosted
Langfuse (step 2 below).

```bash
# 1. install
pip install -e ".[dev]"

# 2. start Langfuse (self-hosted) — see RUNBOOK.md step 1
git clone https://github.com/langfuse/langfuse.git
cd langfuse && docker compose up -d   # UI on http://localhost:3000
# then create an account + project + API keys in the UI

# 3. configure
cp .env.example .env
#    fill in GROQ_API_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
#    (Settings → API Keys in the Langfuse UI), optionally LANGSMITH_API_KEY
#    set ALLOW_LIVE_CALLS=1 only if you want real Groq calls

# 4. sync collector secrets + start this stack
./infrastructure/sync-keys.ps1         # Windows PowerShell
docker compose up -d

# 5. register the Langfuse model pricing (so cost dashboards show USD)
python infrastructure/setup_langfuse_model.py

# 6. collect telemetry
python examples/01_single_call.py      # one trace
python examples/06_synthetic_metrics.py # offline: fills Grafana dashboards only

# 7. test
pytest
```

Full exact steps (including `docker compose down -v` full-wipe recovery)
live in [RUNBOOK.md](RUNBOOK.md). Per-backend details live in [docs/](docs/).

## Example scripts

| Script | Traces | Live API? | What you see |
|---|---|---|---|
| `01_single_call.py` | 1 | yes | 1 trace with clean input/output, cost, tokens |
| `02_multiple_calls.py` | 1 | yes | nested pipeline (retrieve → generate → evaluate) |
| `03_concurrent_calls.py` | 50 | yes (~1 min) | 50 independent searchable traces |
| `04_failures.py` | 3 | **no** | 3 ERROR traces (timeout, rate limit, transient) with retries |
| `05_batch_dashboard.py` | 30 | yes | 30 traces for dashboard data |
| `06_synthetic_metrics.py` | 0 | **no** | synthetic Prometheus observations for Grafana |
| `07_evaluation.py` | 5 | yes | 5 traces with 4 quality scores each |

## Scope guardrails (by design)

This project deliberately does **not** include:

- prompt management, agents, RAG tooling, or productized LLM evaluation
- application-level routing or quota enforcement
- a frontend, chat UI, FastAPI service, or authentication layer
- a production rate limiter

## License

MIT — see [pyproject.toml](pyproject.toml).

Where a backend lacks a native dashboard view (e.g. estimated cost), the lab
**states the limitation** instead of building a replacement UI.

## Safety

- Prompt text and API keys are never recorded as span attributes.  The
  collector additionally strips known sensitive keys (`filter/sensitive`).
- Script 4 uses a **deterministic fake provider** — it never calls the real
  Groq API and cannot exhaust quota.
- Live Groq calls in scripts 1–3 are gated behind `ALLOW_LIVE_CALLS=1`.

## Verification

See `docs/DASHBOARDS.md` for the per-platform attribute-mapping differences and
the post-run verification checklist (trace IDs, parent/child structure, token
counts, error visibility across all three backends).
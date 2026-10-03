# Langfuse — self-hosted setup guide

Langfuse is self-hosted via Docker Compose and receives telemetry through the
OTel Collector's OTLP/HTTP exporter.

## 1. Deploy Langfuse

Use the official self-hosting compose file:

```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse
docker compose up -d   # starts Langfuse + Postgres + (optional) ClickHouse
```

Open `http://localhost:3000`, create an organisation + project, and generate a
**public key** (`pk-lf-...`) and **secret key** (`sk-lf-...`).

## 2. Feed credentials to the collector

The collector reads `LANGFUSE_HOST` and `LANGFUSE_AUTH_HEADER` from its
environment (see `infrastructure/README.md`).  Build the auth header:

```bash
echo -n "pk-lf-xxx:sk-lf-xxx" | base64
```

Put it in the collector's `.env`:

```
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_AUTH_HEADER=<base64 value>
```

Langfuse ingests OTLP traces at `POST /api/public/otel/v1/traces`.

## 3. What Langfuse shows

| Concept | Where in Langfuse | Source attribute |
|---|---|---|
| Trace | Tracing → Sessions | `trace_id` (OTel) |
| Generation span | Tracing → each `generation` | `openinference.span.kind=LLM` |
| Input / output tokens | per-generation "Usage" | `gen_ai.usage.*` |
| Model | per-generation "Model" | `gen_ai.request.model` |
| Latency | per-generation duration | span duration |
| Errors | status = ERROR, exception event | `exception.*` |

## 4. Known mapping notes

- Langfuse maps OpenInference `LLM` spans to its **Generation** entity.  Manual
  workflow spans without `openinference.span.kind` appear as generic **Span**
  entities — this is expected and correct.
- Langfuse does **not** render an estimated-cost column natively.  Cost must be
  computed outside Langfuse (see `observability/pricing.py`) and, if desired,
  attached as a custom metadata attribute (`cost.estimated_usd`).  State this
  limitation in dashboards rather than building a replacement UI.
- `gen_ai.prompt` / `gen_ai.completion` and `llm.input_messages` /
  `llm.output_messages` are **intentionally kept** so Langfuse renders useful
  Input/Output fields. The demo workload is synthetic/non-sensitive trivia
  prompts. Only true secret keys (`authorization`, `x-api-key`, `api_key`)
  are stripped by the collector's `attributes/drop_sensitive` processor.
  If you trace sensitive workloads, configure content redaction
  (e.g. re-add prompt attributes to the drop list) **before** export.
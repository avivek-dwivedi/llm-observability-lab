# Arize Phoenix — self-hosted setup guide

Phoenix runs locally via Docker and receives telemetry over OTLP/gRPC from the
collector.

## 1. Deploy Phoenix

```bash
docker run -p 6006:6006 -p 4317:4317 \
  -e PHOENIX_ENABLE_OTLP=true \
  arizephoenix/phoenix:latest
```

UI: `http://localhost:6006`

The container's gRPC OTLP endpoint is `localhost:4317` **inside the collector
container** use the service name, e.g. `phoenix:4317` (see
`infrastructure/otel-collector.yaml` → `PHOENIX_ENDPOINT`).

## 2. Collector config

```
PHOENIX_ENDPOINT=phoenix:4317
```

The collector's `otlp/phoenix` exporter uses gRPC with `tls.insecure: true` for
local traffic.

## 3. What Phoenix shows

| Concept | Where in Phoenix | Source attribute |
|---|---|---|
| Trace | Traces list | OTel `trace_id` |
| LLM span kind | span "kind: LLM" | `openinference.span.kind=LLM` |
| Token counts | per-span token summary | `llm.token_count.*` / `gen_ai.usage.*` |
| Model | per-span model name | `llm.model_name` |
| Latency | span duration | OTel span duration |
| Errors | status = ERROR | `exception.*` / span status |
| Parent/child | trace waterfall | OTel parent span ID |

## 4. Known mapping notes

- Phoenix is the most OpenInference-native of the three: `openinference.*`
  attributes render first-class.
- Phoenix's **Token Usage** dashboard aggregates `llm.token_count.total`.  If
  you set both `gen_ai.usage.*` and `llm.token_count.*` (this lab does), Phoenix
  prefers the OpenInference names — keep them consistent (we do).
- Phoenix does **not** have a native "estimated cost" dashboard.  Attach cost as
  a span attribute (`cost.estimated_usd`) if you want it visible, and compute it
  with the shared `pricing.py` module — do not rely on per-platform price
  catalogs when comparing dashboards.
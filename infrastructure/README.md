# Infrastructure

This folder contains the OpenTelemetry Collector, Prometheus, and Grafana
configurations for the LLM observability lab.

## Services

| Service | Host port | Container port | Notes |
|---|---|---|---|
| OTel Collector (OTLP/HTTP) | `4318` | `4318` | what the Python SDK talks to |
| OTel Collector (OTLP/gRPC) | `4317` | `4317` | alternative protocol |
| OTel Collector (Prometheus) | `8888` | `8888` | scraped by Prometheus |
| Prometheus | `9095` | `9090` | 45-day retention |
| Grafana | `3001` | `3000` | admin/admin, provisioned dashboards |
| Phoenix | `6006` | `6006` | self-hosted web UI |
| Langfuse | `3000` | `3000` | external (already running) |

## `otel-collector.yaml`

Two pipelines:

```
OTLP receiver (4318/4317)
  -> attributes/drop_sensitive
  -> batch
  -> [ Langfuse (OTLP/HTTP) | Phoenix (OTLP/gRPC) | LangSmith (OTLP/HTTP) ]
```

### Keeping credentials out of the source

Every secret is read from the collector process's environment (`${env:...}`).
Create a `.env` file next to the collector (or pass env vars to the container)
with at least:

```bash
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_AUTH_HEADER=<base64 of "pk-lf-...:sk-lf-...">
PHOENIX_ENDPOINT=phoenix:4317
LANGSMITH_OTLP_ENDPOINT=https://api.smith.langchain.com/otel
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=llm-observability-lab
```

`LANGFUSE_AUTH_HEADER` is the base64 of `public_key:secret_key`:

```bash
echo -n "pk-lf-xxx:sk-lf-xxx" | base64
```

## Running the collector

```bash
# from this directory, with the contrib image that has otlphttp + otlp exporters
docker run --rm -p 4318:4318 -p 4317:4317 -p 13133:13133 \
  --env-file .env \
  -v "$(pwd)/otel-collector.yaml:/etc/otelcol/config.yaml" \
  otel/opentelemetry-collector-contrib:latest
```

## Verifying the fan-out

After running any example script, check each backend:

1. **Langfuse** — open `http://localhost:3000`, look for the trace; generation
   spans appear under the `gen_ai` operation.
2. **Phoenix** — open `http://localhost:6006`, the trace should show a root
   workflow span (for scripts 2-4) with child LLM spans.
3. **LangSmith** — open the LangSmith UI for the configured project; traces are
   grouped by `Langsmith-Project` header.

If one backend shows traces but another does not, check the collector logs for
exporter-level errors — do **not** assume all backends interpret attributes
identically (see `docs/DASHBOARDS.md` for known mapping differences).
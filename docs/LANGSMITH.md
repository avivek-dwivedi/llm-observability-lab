# LangSmith — SaaS integration guide

LangSmith is SaaS-only and ingests OTLP via an authenticated HTTP endpoint.

## 1. Get credentials

1. Sign in at https://smith.langchain.com.
2. Create a project (e.g. `llm-observability-lab`).
3. Generate an API key (`lsv2_pt_...`).

## 2. Collector config

LangSmith's OTLP endpoint is `https://api.smith.langchain.com/otel`.  Auth is
two headers:

| Header | Value |
|---|---|
| `x-api-key` | your `lsv2_pt_...` key |
| `Langsmith-Project` | project name, e.g. `llm-observability-lab` |

In the collector `.env`:

```
LANGSMITH_OTLP_ENDPOINT=https://api.smith.langchain.com/otel
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=llm-observability-lab
```

The collector's `otlphttp/langsmith` exporter forwards traces to
`POST <endpoint>/v1/traces`.

## 3. What LangSmith shows

| Concept | Where in LangSmith | Source attribute |
|---|---|---|
| Trace | Traces → project | OTel `trace_id` |
| Run / span | per-run detail | OTel span |
| Model | run metadata | `gen_ai.request.model` |
| Tokens | run "usage" | `gen_ai.usage.*` |
| Latency | run duration | OTel span duration |
| Errors | run status = ERROR | `exception.*` |

## 4. Known mapping notes

- LangSmith maps OTel spans to **Runs**.  `openinference.span.kind=LLM` runs
  appear as **LLM** runs; manual workflow spans appear as **Chain** runs.
- LangSmith's token dashboard uses `gen_ai.usage.input_tokens` /
  `gen_ai.usage.output_tokens`.  It does not natively render cost; compute cost
  with `pricing.py` and optionally attach `cost.estimated_usd`.
- Because LangSmith is SaaS, network egress from the collector must reach
  `api.smith.langchain.com` over HTTPS.  Verify the collector logs show HTTP
  200 from the exporter after the first run.
"""Single OpenTelemetry pipeline + manual Groq call instrumentation.

Design rules (from the project brief):
- One OTel TracerProvider, one exporter, one instrumentation pass.
- We do NOT use OpenInference's auto-instrumentation for Groq because it
  serializes the entire Groq SDK request object (including ``groq.Omit``
  sentinel values) as the input — producing ugly output in Langfuse like
  ``citation_options: <groq.Omit object at 0x...>``.
- Instead, we create manual ``Completions`` spans with clean, minimal
  ``llm.input_messages`` / ``llm.output_messages`` JSON attributes that
  Langfuse and Phoenix render properly.
- Add manual spans ONLY for workflow-level information (logical root spans,
  retries, etc.).
- Do not record secrets or sensitive prompt text.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPSpanExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GRPCSpanExporter,
)

from observability.identity import resource_attributes, SERVICE_VERSION

log = logging.getLogger("llm_obs.instrumentation")

_PROVIDER: TracerProvider | None = None
_INSTRUMENTED = False


def _build_exporter() -> SpanExporter:
    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
    )
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

    # OTLP/HTTP spans are posted to <endpoint>/v1/traces.
    if protocol.startswith("http"):
        url = endpoint.rstrip("/")
        if not url.endswith("/v1/traces"):
            url = f"{url}/v1/traces"
        log.info("OTLP exporter: HTTP %s", url)
        return HTTPSpanExporter(endpoint=url)

    # OTLP/gRPC uses the raw endpoint (no path suffix).
    log.info("OTLP exporter: gRPC %s", endpoint)
    return GRPCSpanExporter(endpoint=endpoint, insecure=True)


def configure_otel(service_name: str | None = None) -> TracerProvider:
    """Initialise ONE TracerProvider with a single OTLP exporter.

    Safe to call multiple times: subsequent calls return the existing provider
    and do NOT re-instrument (avoids double instrumentation).
    """
    global _PROVIDER, _INSTRUMENTED

    if _PROVIDER is not None:
        return _PROVIDER

    resource = Resource.create(resource_attributes(service_name_override=service_name))

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            _build_exporter(),
            # Flush quickly enough for demo scripts that exit right after.
            max_export_batch_size=32,
            export_timeout_millis=5000,
        )
    )
    trace.set_tracer_provider(provider)
    _PROVIDER = provider

    if not _INSTRUMENTED:
        # We do NOT use OpenInference auto-instrumentation for Groq.
        # It serializes the entire Groq SDK request object (with groq.Omit
        # sentinels) as input, producing ugly output in Langfuse.
        # Instead, each example script creates manual Completions spans
        # via completions_span() with clean llm.input_messages / llm.output_messages.
        log.info("Manual Completions span instrumentation (no auto-instrument)")
        _INSTRUMENTED = True

    return provider


@contextmanager
def workflow_span(
    name: str,
    attributes: dict | None = None,
) -> Iterator[trace.Span]:
    """Create a manual root/parent span for a logical LLM workflow.

    Use this helper to wrap a group of calls so each Completions span is a
    child of a single workflow span.
    """
    tracer = trace.get_tracer("llm-observability.workflow")
    with tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span


@contextmanager
def completions_span(
    name: str = "Completions",
    *,
    model: str = "",
    provider: str = "groq",
    prompt: str = "",
    response: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    max_tokens: int = 0,
    temperature: float = 0.0,
    user_id: str = "",
    session_id: str = "",
    extra_attributes: dict | None = None,
) -> Iterator[trace.Span]:
    """Create a manual Completions child span with clean input/output.

    This replaces the OpenInference auto-instrumentation. Instead of
    serializing the entire Groq SDK request object, we set minimal,
    clean attributes that Langfuse and Phoenix can render properly:

      - ``llm.input_messages``  → JSON: [{"role": "user", "content": prompt}]
      - ``llm.output_messages`` → JSON: [{"role": "assistant", "content": response}]
      - ``gen_ai.prompt``       → raw prompt string
      - ``gen_ai.completion``   → raw response string
      - ``gen_ai.request.model``  / ``gen_ai.response.model``
      - ``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens``
      - ``openinference.span.kind`` → "LLM"
      - ``llm.model_name`` → model
      - ``llm.token_count.prompt`` / ``llm.token_count.completion`` / ``llm.token_count.total``

    Usage::

        with completions_span(model="allam-2-7b", prompt="Hello") as span:
            resp = client.chat.completions.create(...)
            span.set_attribute("gen_ai.completion", resp.choices[0].message.content)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
    """
    import json as _json

    tracer = trace.get_tracer("llm-observability.completions")
    attrs: dict = {
        "gen_ai.system": provider,
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": model,
        "openinference.span.kind": "LLM",
        "llm.model_name": model,
    }
    if max_tokens:
        attrs["gen_ai.request.max_tokens"] = max_tokens
    attrs["gen_ai.request.temperature"] = temperature

    # Langfuse-specific identity attributes. Langfuse maps these on the ROOT
    # span to trace.userId / trace.sessionId, which powers the Users view,
    # Top-Users-by-cost panels and session grouping.
    if user_id:
        attrs["langfuse.user.id"] = user_id
    if session_id:
        attrs["langfuse.session.id"] = session_id

    # Clean input messages — the key fix for the groq.Omit problem
    if prompt:
        input_msgs = [{"role": "user", "content": prompt}]
        attrs["llm.input_messages"] = _json.dumps(input_msgs, ensure_ascii=False)
        attrs["gen_ai.prompt"] = prompt

    # Clean output messages
    if response:
        output_msgs = [{"role": "assistant", "content": response}]
        attrs["llm.output_messages"] = _json.dumps(output_msgs, ensure_ascii=False)
        attrs["gen_ai.completion"] = response

    # Token counts
    if input_tokens:
        attrs["gen_ai.usage.input_tokens"] = input_tokens
        attrs["llm.token_count.prompt"] = input_tokens
    if output_tokens:
        attrs["gen_ai.usage.output_tokens"] = output_tokens
        attrs["llm.token_count.completion"] = output_tokens
    if input_tokens or output_tokens:
        attrs["llm.token_count.total"] = input_tokens + output_tokens

    if extra_attributes:
        attrs.update(extra_attributes)

    with tracer.start_as_current_span(name, attributes=attrs) as span:
        yield span


def shutdown_otel() -> None:
    """Flush pending spans and shut down the provider (call before exit)."""
    global _PROVIDER
    if _PROVIDER is not None:
        try:
            _PROVIDER.force_flush()
            _PROVIDER.shutdown()
        finally:
            _PROVIDER = None
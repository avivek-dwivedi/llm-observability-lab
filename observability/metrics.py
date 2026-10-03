"""V2 metrics instrumentation for Prometheus/Grafana SLO monitoring.

This module adds OTel metrics (counters + histogram) that flow through the
existing collector's new metrics pipeline → Prometheus → Grafana.

Metrics exposed (with the `llm_obs_` prefix after the collector's namespace):

Counters:
  llm_requests_total            — completed logical requests
  llm_tokens_total              — LLM tokens (dimension: token_type=input|output)
  llm_estimated_cost_usd_total  — estimated cost in USD
  llm_api_attempts_total        — individual API attempts (dimension: outcome)

Histogram:
  llm_request_duration_seconds  — end-to-end logical-request latency
    buckets: 0.1, 0.25, 0.5, 1, 2, 4, 8, 16  (4s boundary included per SLO)

Labels (bounded, no high-cardinality):
  service, model, workflow, environment, result

Design rules:
- No user IDs or trace IDs as Prometheus labels (they'd blow up cardinality).
- One MeterProvider, one OTLP metrics exporter (same endpoint as traces).
- Short-running scripts MUST call flush_metrics() before exiting.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import Meter, Counter, Histogram
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
    InMemoryMetricReader,
)
from opentelemetry.sdk.metrics.export import MetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as HTTPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as GRPCMetricExporter,
)

from observability.identity import (
    base_labels,
    resource_attributes,
    SERVICE_VERSION,
)

log = logging.getLogger("llm_obs.metrics")

_METER_PROVIDER: MeterProvider | None = None
_METER: Meter | None = None

# Instruments (created once, reused)
_requests_counter: Counter | None = None
_tokens_counter: Counter | None = None
_cost_counter: Counter | None = None
_attempts_counter: Counter | None = None
_duration_histogram: Histogram | None = None

# Latency histogram buckets — 4s boundary included for the SLO.
_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)


def _build_metric_exporter() -> MetricExporter:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

    if protocol.startswith("http"):
        url = endpoint.rstrip("/")
        if not url.endswith("/v1/metrics"):
            url = f"{url}/v1/metrics"
        log.info("OTLP metrics exporter: HTTP %s", url)
        return HTTPMetricExporter(endpoint=url)

    log.info("OTLP metrics exporter: gRPC %s", endpoint)
    return GRPCMetricExporter(endpoint=endpoint, insecure=True)


def configure_metrics(service_name: str | None = None) -> MeterProvider:
    """Initialise ONE MeterProvider with a single OTLP metrics exporter.

    Safe to call multiple times: returns the existing provider.
    Uses a short export interval (2s) so short-running demo scripts flush
    metrics before exit.  Still call flush_metrics() for safety.
    """
    global _METER_PROVIDER, _METER
    global _requests_counter, _tokens_counter, _cost_counter
    global _attempts_counter, _duration_histogram

    if _METER_PROVIDER is not None:
        return _METER_PROVIDER

    resource = Resource.create(resource_attributes(service_name_override=service_name))

    exporter = _build_metric_exporter()
    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=2000,
        export_timeout_millis=5000,
    )

    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    _METER_PROVIDER = provider
    _METER = provider.get_meter("llm-observability.metrics", SERVICE_VERSION)

    # --- Create instruments -------------------------------------------------
    _requests_counter = _METER.create_counter(
        name="llm_requests_total",
        description="Completed logical LLM requests",
        unit="1",
    )
    _tokens_counter = _METER.create_counter(
        name="llm_tokens_total",
        description="LLM tokens consumed",
        unit="1",
    )
    _cost_counter = _METER.create_counter(
        name="llm_estimated_cost_usd_total",
        description="Estimated cost in USD (configured estimate, not a bill)",
        unit="USD",
    )
    _attempts_counter = _METER.create_counter(
        name="llm_api_attempts_total",
        description="Individual API attempts (including retries)",
        unit="1",
    )
    _duration_histogram = _METER.create_histogram(
        name="llm_request_duration_seconds",
        description="End-to-end logical-request latency",
        unit="s",
        explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
    )

    log.info("Metrics instruments created (counters + histogram)")
    return provider


def _base_labels(
    *,
    model: str = "",
    workflow: str = "",
    environment: str | None = None,
    result: str = "success",
) -> dict:
    """Build the bounded label set."""
    return {
        **base_labels(),
        "model": model or os.getenv("GROQ_MODEL", "allam-2-7b"),
        "workflow": workflow,
        "result": result,
    }


def record_request(
    *,
    model: str = "",
    workflow: str = "",
    result: str = "success",
    environment: str | None = None,
) -> None:
    """Increment the completed-requests counter."""
    if _requests_counter is None:
        log.warning("Metrics not configured — call configure_metrics() first")
        return
    labels = _base_labels(
        model=model, workflow=workflow, result=result, environment=environment
    )
    _requests_counter.add(1, labels)


def record_tokens(
    *,
    input_tokens: int,
    output_tokens: int,
    model: str = "",
    workflow: str = "",
    environment: str | None = None,
) -> None:
    """Increment the token counters (input + output separately)."""
    if _tokens_counter is None:
        return
    base = _base_labels(
        model=model, workflow=workflow, environment=environment
    )
    if input_tokens > 0:
        _tokens_counter.add(input_tokens, {**base, "token_type": "input"})
    if output_tokens > 0:
        _tokens_counter.add(output_tokens, {**base, "token_type": "output"})


def record_cost(
    *,
    cost_usd: float,
    model: str = "",
    workflow: str = "",
    environment: str | None = None,
) -> None:
    """Increment the estimated-cost counter (in USD)."""
    if _cost_counter is None:
        return
    labels = _base_labels(
        model=model, workflow=workflow, environment=environment
    )
    _cost_counter.add(cost_usd, labels)


def record_attempt(
    *,
    outcome: str,
    model: str = "",
    workflow: str = "",
    attempt_number: int = 1,
    environment: str | None = None,
) -> None:
    """Increment the API-attempts counter (one per attempt, including retries)."""
    if _attempts_counter is None:
        return
    labels = _base_labels(
        model=model, workflow=workflow, environment=environment
    )
    _attempts_counter.add(
        1,
        {**labels, "outcome": outcome, "attempt": str(attempt_number)},
    )


def record_duration(
    *,
    duration_s: float,
    model: str = "",
    workflow: str = "",
    result: str = "success",
    environment: str | None = None,
) -> None:
    """Record an end-to-end logical-request latency observation."""
    if _duration_histogram is None:
        return
    labels = _base_labels(
        model=model, workflow=workflow, result=result, environment=environment
    )
    _duration_histogram.record(duration_s, labels)


def flush_metrics() -> None:
    """Force-flush pending metrics.  Call before process exit in short scripts."""
    global _METER_PROVIDER
    if _METER_PROVIDER is not None:
        try:
            _METER_PROVIDER.force_flush()
            log.info("Metrics flushed")
        except Exception as exc:
            log.warning("Metrics flush failed: %s", exc)


def shutdown_metrics() -> None:
    """Flush and shut down the meter provider."""
    global _METER_PROVIDER, _METER
    global _requests_counter, _tokens_counter, _cost_counter
    global _attempts_counter, _duration_histogram
    if _METER_PROVIDER is not None:
        try:
            _METER_PROVIDER.force_flush()
            _METER_PROVIDER.shutdown()
        finally:
            _METER_PROVIDER = None
            _METER = None
            _requests_counter = None
            _tokens_counter = None
            _cost_counter = None
            _attempts_counter = None
            _duration_histogram = None
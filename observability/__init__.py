"""Multi-platform LLM observability lab.

This package wires the Groq SDK to OpenTelemetry through OpenInference's
automatic Groq instrumentation, adds a single manual workflow span helper,
cost telemetry, metadata utilities, and V2 metrics + SLO monitoring.
It deliberately avoids chatbot / agent / API-server concerns — its only job
is to *observe* LLM calls.
"""

from observability.instrumentation import (
    configure_otel,
    workflow_span,
    shutdown_otel,
)
from observability.usage import extract_usage, zero_usage
from observability.pricing import estimate_cost, PricingConfig
from observability.metadata import build_attributes

# V2 — metrics + SLOs
from observability.metrics import (
    configure_metrics,
    flush_metrics,
    shutdown_metrics,
    record_request,
    record_tokens,
    record_cost,
    record_attempt,
    record_duration,
)
from observability.slos import (
    evaluate_success_slo,
    evaluate_latency_slo,
    format_slo_report,
    SLOResult,
    MIN_SAMPLES,
    SLO_SUCCESS_RATE_7D,
    SLO_LATENCY_PCT_UNDER_4S,
    HYPOTHETICAL_MONTHLY_SLA,
)

__all__ = [
    # V1
    "configure_otel",
    "workflow_span",
    "shutdown_otel",
    "extract_usage",
    "zero_usage",
    "estimate_cost",
    "PricingConfig",
    "build_attributes",
    # V2
    "configure_metrics",
    "flush_metrics",
    "shutdown_metrics",
    "record_request",
    "record_tokens",
    "record_cost",
    "record_attempt",
    "record_duration",
    "evaluate_success_slo",
    "evaluate_latency_slo",
    "format_slo_report",
    "SLOResult",
    "MIN_SAMPLES",
    "SLO_SUCCESS_RATE_7D",
    "SLO_LATENCY_PCT_UNDER_4S",
    "HYPOTHETICAL_MONTHLY_SLA",
]
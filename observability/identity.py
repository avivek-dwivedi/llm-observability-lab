"""Shared OpenTelemetry resource identity for traces AND metrics.

Single source of truth so both telemetry signals describe the same service:

- ``service.name``            — OTEL_SERVICE_NAME env or DEFAULT_SERVICE
- ``service.version``         — __version__ (single place; was previously
                                 duplicated as 0.1.0 in traces and 0.2.0
                                 in metrics)
- ``deployment.environment``  — OTEL_ENV env or DEFAULT_ENV

Avoids tracing/metrics identity drift without any configuration framework.
"""

from __future__ import annotations

import os

# Keep the literal defaults here so instrumentation.py and metrics.py stop
# carrying their own copies (they previously drifted: 0.1.0 vs 0.2.0).
DEFAULT_SERVICE = "llm-observability-lab"
DEFAULT_ENV = "default"
SERVICE_VERSION = "0.2.0"  # keep in sync with pyproject.toml [project] version


def service_name() -> str:
    return os.getenv("OTEL_SERVICE_NAME", DEFAULT_SERVICE)


def deployment_environment() -> str:
    return os.getenv("OTEL_ENV", DEFAULT_ENV)


def resource_attributes(
    *,
    service_name_override: str | None = None,
    env_override: str | None = None,
) -> dict:
    """Attributes shared by the trace and metric Resource objects.

    Explicit overrides (from ``configure_otel(service_name=...)`` and
    ``configure_metrics(service_name=...)``) win over the environment.
    """
    return {
        "service.name": service_name_override or service_name(),
        "service.version": SERVICE_VERSION,
        "deployment.environment": env_override or deployment_environment(),
    }


def base_labels() -> dict:
    """Bounded Prometheus label set shared by all metric instruments."""
    return {
        "service": service_name(),
        "environment": deployment_environment(),
    }
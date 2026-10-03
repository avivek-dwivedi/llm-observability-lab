"""Script 4 — Failure observations with real error levels.

3 failure types, each as its OWN trace:
  1. failure_timeout    — 3 retry attempts, all timeout → EXHAUSTED
  2. failure_rate_limit — 3 retry attempts, all 429 → EXHAUSTED
  3. failure_transient  — attempt 1 fails (500), attempt 2 succeeds → RECOVERED

Each trace has REAL error levels propagated from actual exceptions:
  - Child attempt spans: record_exception() + set_status(ERROR) on each failure
  - Root trace: records the LAST exception when exhausted
  - Langfuse shows 🚨 automatically from the ERROR status code
  - The exception object is recorded (not just a string) so Langfuse renders
    the full stack trace and exception type in its UI

Standard OpenTelemetry error semantics:
  - StatusCode.ERROR = the operation failed
  - span.record_exception(exc) = records the exception event with type, message, stack
  - These are what Langfuse/Phoenix/LangSmith use to show error indicators

No live Groq calls — uses a deterministic fake provider.
"""

from __future__ import annotations

import time
from contextlib import suppress

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from observability.instrumentation import workflow_span
from observability.metadata import build_attributes

from examples._common import ensure_otel, model_name, shutdown_all


# ---------------------------------------------------------------------------
# Fake exceptions — simulating real API errors
# ---------------------------------------------------------------------------

class FakeTimeoutError(Exception):
    """Simulates a read timeout (HTTP 408 / gateway timeout)."""
    pass


class FakeRateLimitError(Exception):
    """Simulates a 429 Too Many Requests response."""
    pass


class FakeServerError(Exception):
    """Simulates a 500 Internal Server Error (transient)."""
    pass


# Failure scenario configurations
FAILURE_SCENARIOS = {
    "timeout": {
        "error_cls": FakeTimeoutError,
        "error_msg": "simulated read timeout after 30s",
        "failure_reason": "timeout",
        "failure_type": "TimeoutError",
        "http_status": 408,
    },
    "rate_limit": {
        "error_cls": FakeRateLimitError,
        "error_msg": "429 Too Many Requests — rate limit exceeded",
        "failure_reason": "rate_limit",
        "failure_type": "RateLimitError",
        "http_status": 429,
    },
    "transient": {
        "error_cls": FakeServerError,
        "error_msg": "500 Internal Server Error (transient)",
        "failure_reason": "transient_500",
        "failure_type": "ServerError",
        "http_status": 500,
    },
}


def _fake_call(scenario: str, attempt: int) -> str:
    """Deterministic fake provider — no network, no real quota use."""
    time.sleep(0.02)
    if scenario == "timeout":
        raise FakeTimeoutError("simulated read timeout after 30s")
    if scenario == "rate_limit":
        raise FakeRateLimitError("429 Too Many Requests — rate limit exceeded")
    if scenario == "transient":
        if attempt < 2:
            raise FakeServerError("500 Internal Server Error (transient)")
        return "ok — recovered on retry"
    raise ValueError(f"unknown scenario {scenario}")


# ---------------------------------------------------------------------------
# Run one failure scenario as its own trace
# ---------------------------------------------------------------------------

def _run_failure_scenario(scenario: str, max_attempts: int = 3) -> None:
    """Run one failure scenario as its own root trace.

    Each retry attempt is a child span. When an attempt fails:
      - span.record_exception(exc)  → records the actual exception object
      - span.set_status(ERROR)      → sets the OTel error status

    When ALL attempts are exhausted:
      - root.record_exception(last_exc)  → root trace shows the exception
      - root.set_status(ERROR)           → root trace gets ERROR level
      - Langfuse shows 🚨 on the trace row automatically

    When a transient error recovers:
      - The failed attempt span keeps its ERROR status (it DID fail)
      - The root trace stays OK (the overall operation succeeded)
      - root.set_attribute("failure.recovered", True)
    """
    cfg = FAILURE_SCENARIOS[scenario]
    tracer = trace.get_tracer("llm-observability.failures")
    model = model_name()
    last_exception: Exception | None = None

    with workflow_span(
        f"failure_{scenario}",
        attributes=build_attributes(
            model=model, operation="workflow",
            extra={
                "failure.reason": cfg["failure_reason"],
                "failure.type": cfg["failure_type"],
                "failure.http_status": cfg["http_status"],
                "retry.max_attempts": max_attempts,
                "workflow.kind": "failure_observation",
            },
        ),
    ) as root:
        print(f"\n  --- failure_{scenario} ---")
        print(f"  Failure reason: {cfg['failure_reason']}")
        print(f"  Error type:     {cfg['failure_type']}")
        print(f"  HTTP status:    {cfg['http_status']}")

        for attempt in range(1, max_attempts + 1):
            with tracer.start_as_current_span(
                f"attempt_{attempt}",
                attributes=build_attributes(
                    model=model, operation="chat",
                    extra={
                        "retry.attempt": attempt,
                        "retry.scenario": scenario,
                        "retry.max_attempts": max_attempts,
                    },
                ),
            ) as span:
                start = time.perf_counter()
                try:
                    result = _fake_call(scenario, attempt)
                    # SUCCESS
                    span.set_attribute("retry.outcome", "success")
                    span.set_attribute("failure.recovered", True)
                    span.set_attribute("gen_ai.completion", result)
                    print(f"  attempt {attempt}: SUCCESS (recovered)")
                    dur = time.perf_counter() - start

                    from observability.metrics import record_attempt, record_duration, record_request
                    record_attempt(outcome="success", model=model,
                                   workflow=f"failure_{scenario}", attempt_number=attempt)
                    record_duration(duration_s=dur, model=model,
                                    workflow=f"failure_{scenario}", result="success")
                    record_request(model=model, workflow=f"failure_{scenario}", result="success")

                    # Root: operation recovered — keep OK status
                    root.set_attribute("failure.final_outcome", "recovered")
                    root.set_attribute("failure.recovered_on_attempt", attempt)
                    root.set_attribute("failure.recovered", True)
                    return

                except Exception as exc:
                    # Record the ACTUAL exception on the child span
                    # This is what makes Langfuse show the error details
                    last_exception = exc
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.set_attribute("retry.outcome", "error")
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_attribute("error.message", str(exc))
                    span.set_attribute("failure.reason", cfg["failure_reason"])
                    span.set_attribute("failure.type", cfg["failure_type"])
                    span.set_attribute("failure.http_status", cfg["http_status"])
                    dur = time.perf_counter() - start
                    print(f"  attempt {attempt}: {type(exc).__name__} — {exc} ({dur:.3f}s)")

                    from observability.metrics import record_attempt, record_duration
                    record_attempt(outcome=type(exc).__name__, model=model,
                                   workflow=f"failure_{scenario}", attempt_number=attempt)
                    record_duration(duration_s=dur, model=model,
                                    workflow=f"failure_{scenario}", result=type(exc).__name__)

                    if attempt == max_attempts:
                        # ALL attempts exhausted — set ERROR on root trace
                        # Record the last actual exception on the root span
                        # so Langfuse shows 🚨 + exception details on the trace row
                        root.record_exception(last_exception)
                        root.set_status(Status(
                            StatusCode.ERROR,
                            f"{cfg['failure_type']}: exhausted {max_attempts} attempts — {cfg['failure_reason']}"
                        ))
                        root.set_attribute("failure.final_outcome", "exhausted")
                        root.set_attribute("failure.recovered", False)
                        root.set_attribute("error.type", cfg["failure_type"])
                        root.set_attribute("error.message", str(last_exception))

                        print(f"  → EXHAUSTED {max_attempts} attempts — failure: {cfg['failure_reason']}")
                        print(f"  → Root trace set to ERROR level with exception recorded")

                        from observability.metrics import record_request
                        record_request(model=model, workflow=f"failure_{scenario}",
                                       result=cfg["failure_type"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_failures() -> None:
    ensure_otel()
    model = model_name()

    print(f"{'='*60}")
    print(f"  FAILURE OBSERVATIONS — 3 traces with real error levels")
    print(f"  Model: {model} | No live API calls (fake provider)")
    print(f"{'='*60}")
    print(f"  Each failure type is its own trace:")
    print(f"    - Real exception recorded via span.record_exception()")
    print(f"    - ERROR status set via span.set_status(StatusCode.ERROR)")
    print(f"    - Langfuse shows 🚨 automatically from ERROR status")
    print(f"    - Failure reason, type, HTTP status as attributes")
    print(f"    - Retry attempts as child spans")

    # 1. Timeout — all 3 attempts fail → root trace ERROR
    _run_failure_scenario("timeout", max_attempts=3)

    # 2. Rate limit — all 3 attempts fail → root trace ERROR
    _run_failure_scenario("rate_limit", max_attempts=3)

    # 3. Transient — attempt 1 fails (child ERROR), attempt 2 succeeds → root OK
    _run_failure_scenario("transient", max_attempts=3)

    print(f"\n{'='*60}")
    print(f"  3 failure traces created:")
    print(f"    1. failure_timeout    — 🚨 ERROR (exhausted, TimeoutError recorded)")
    print(f"    2. failure_rate_limit — 🚨 ERROR (exhausted, RateLimitError recorded)")
    print(f"    3. failure_transient  — ✅ OK (recovered, child attempt_1 has ERROR)")
    print(f"{'='*60}")
    print(f"  In Langfuse:")
    print(f"    - Traces 1 & 2 show 🚨 error icon on the trace row")
    print(f"    - Click trace → see exception details + stack trace")
    print(f"    - Trace 3 shows OK, but expand → attempt_1 has ERROR status")


if __name__ == "__main__":
    try:
        run_failures()
    finally:
        with suppress(Exception):
            shutdown_all()
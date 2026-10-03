"""Script 6 — 3 scenarios for 3 Grafana dashboards.

Scenario 1 (normal):          500 calls, 99% success, fast (0.15-0.5s)
Scenario 2 (llm_degraded):    500 calls, 92% success, slow (1-6s), retries
Scenario 3 (system_failure):  500 calls, 55% success, mixed, rate limits + timeouts

Each scenario uses a different `workflow` label so dashboards filter independently.
No live API calls — all synthetic.

Run: .venv\\Scripts\\python.exe examples\\06_synthetic_metrics.py
"""

from __future__ import annotations

import os
import random
from contextlib import suppress

from observability.instrumentation import configure_otel, shutdown_otel
from observability.metrics import configure_metrics, flush_metrics, shutdown_metrics

MODEL = os.getenv("GROQ_MODEL", "allam-2-7b")
random.seed(42)


def _emit(name: str, n: int, success_rate: float,
          latency_range: tuple[float, float],
          error_type: str | None = None,
          retry_rate: float = 0.0) -> None:
    from observability.metrics import (
        record_request, record_tokens, record_cost, record_duration, record_attempt,
    )
    from observability.pricing import estimate_cost
    from observability.usage import Usage

    print(f"\n  [{name}] {n} calls | success={success_rate:.0%} | "
          f"latency={latency_range[0]:.1f}-{latency_range[1]:.1f}s | "
          f"error={error_type or 'none'} | retry={retry_rate:.0%}")

    for i in range(n):
        is_success = random.random() < success_rate
        latency = random.uniform(*latency_range)
        in_tok = random.randint(10, 40)
        out_tok = random.randint(20, 300) if is_success else 0
        result = "success" if is_success else (error_type or "error")

        record_request(model=MODEL, workflow=name, result=result)
        record_tokens(input_tokens=in_tok, output_tokens=out_tok,
                      model=MODEL, workflow=name)
        record_duration(duration_s=latency, model=MODEL, workflow=name, result=result)

        # First attempt
        record_attempt(outcome="success" if is_success else (error_type or "error"),
                        model=MODEL, workflow=name, attempt_number=1)

        # Retries (if any)
        if not is_success and random.random() < retry_rate:
            retry_success = random.random() < 0.3
            record_attempt(
                outcome="success" if retry_success else (error_type or "error"),
                model=MODEL, workflow=name, attempt_number=2)

        if is_success and (in_tok > 0 or out_tok > 0):
            usage = Usage(in_tok, out_tok, in_tok + out_tok)
            cost = estimate_cost(usage, MODEL)
            if cost:
                record_cost(cost_usd=cost.total_cost, model=MODEL, workflow=name)

        if (i + 1) % 100 == 0:
            print(f"    ... {i+1}/{n}")

    successful = int(n * success_rate)
    total_in = n * 25
    total_out = successful * 160
    total_usage = Usage(total_in, total_out, total_in + total_out)
    cost = estimate_cost(total_usage, MODEL)
    print(f"    Done: {successful} ok, {n - successful} errors, "
          f"{total_in + total_out} tokens, ${cost.total_cost:.4f}" if cost else "")


def run() -> None:
    configure_otel()
    configure_metrics()

    print("=" * 60)
    print("  3 SCENARIOS — 3 Grafana dashboards")
    print("=" * 60)

    # 1. Normal — healthy system
    _emit("normal", 500, 0.99, (0.15, 0.50))

    # 2. LLM Degraded — slow LLM, some retries, cost up
    _emit("llm_degraded", 500, 0.92, (1.0, 6.0), error_type="LLMTimeoutError", retry_rate=0.5)

    # 3. System Failure — rate limits + timeouts, many errors
    _emit("system_failure", 500, 0.55, (0.3, 4.0), error_type="RateLimitError", retry_rate=0.8)

    print(f"\n{'='*60}")
    print("  DONE — 1500 observations across 3 scenarios")
    print(f"{'='*60}")
    print("  Dashboard 1 (Normal):          99% success, P95 ~0.5s, $0.39")
    print("  Dashboard 2 (LLM Degraded):    92% success, P95 ~6s,  retries, cost up")
    print("  Dashboard 3 (System Failure):  55% success, many errors, budget gone")


if __name__ == "__main__":
    try:
        run()
    finally:
        with suppress(Exception):
            flush_metrics()
            shutdown_metrics()
            shutdown_otel()
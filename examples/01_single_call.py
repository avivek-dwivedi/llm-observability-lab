"""Script 1 — Single LLM call (one standalone trace).

One Groq API call = ONE trace in Langfuse.
The trace name is "single_call" and it contains one Completions span with:
  - Clean Input (prompt text)
  - Clean Output (response text)
  - Token counts, cost, latency

This is the simplest pattern: 1 call → 1 trace → 1 Completions span.

Set ALLOW_LIVE_CALLS=1 in .env for real Groq calls.
"""

from __future__ import annotations

from contextlib import suppress

from observability.pricing import estimate_cost

from examples._common import (
    ensure_otel,
    live_calls_allowed,
    make_groq_client,
    individual_call,
    model_name,
    summarise,
    shutdown_all,
    CallResult,
    SYNTHETIC_PROMPTS,
)


def run_single_call() -> CallResult:
    ensure_otel()
    model = model_name()
    prompt = SYNTHETIC_PROMPTS[0]

    print(f"{'='*60}")
    print(f"  SINGLE CALL — 1 trace, 1 Completions span")
    print(f"  Model: {model} | Prompt: '{prompt}'")
    print(f"{'='*60}")

    if live_calls_allowed():
        client = make_groq_client()
        result = individual_call(
            client,
            trace_name="single_call",
            prompt=prompt,
            max_tokens=64,
            workflow="single_call",
        )
    else:
        print("\n  [dry-run] Set ALLOW_LIVE_CALLS=1 for real API calls")
        from observability.usage import zero_usage
        result = CallResult(
            text="(dry-run)",
            usage_input=12, usage_output=14, duration_s=0.0,
            model=model, trace_id="0"*32, span_id="0"*16,
        )

    print(f"\n  {summarise(result)}")
    print(f"  Response: {result.text[:80]}")

    usage_in = result.usage_input
    usage_out = result.usage_output
    from observability.usage import Usage
    cost = estimate_cost(Usage(usage_in, usage_out, usage_in + usage_out), model)
    if cost is None:
        print("  Cost:     missing pricing")
    else:
        print(f"  Cost:     ~${cost.total_cost:.6f} (configured estimate, not a bill)")

    print(f"\n  In Langfuse: look for trace 'single_call'")
    print(f"  Click it → see Completions span with clean Input/Output")

    return result


if __name__ == "__main__":
    try:
        run_single_call()
    finally:
        with suppress(Exception):
            shutdown_all()
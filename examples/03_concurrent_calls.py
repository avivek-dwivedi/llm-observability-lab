"""Script 3 — Multiple individual LLM calls (25-30 separate traces).

Each call is its OWN trace in Langfuse — no parent workflow span.
This simulates a real application making individual API calls:
  - Each trace is independently searchable
  - Each trace has its own input/output/cost/latency
  - Each trace row in Langfuse shows the prompt and response

Respects 30 RPM rate limit (2s delay between sequential calls).

Compares sequential vs concurrent execution:
  - Sequential: 2s delay between calls (rate-limited)
  - Concurrent: all fire at once (within rate limit)

Set ALLOW_LIVE_CALLS=1 in .env before running.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from contextlib import suppress

from observability.usage import Usage

from examples._common import (
    ensure_otel,
    live_calls_allowed,
    make_groq_client,
    model_name,
    individual_call,
    shutdown_all,
    SYNTHETIC_PROMPTS,
    CallResult,
)

# Rate limit: 30 RPM = 1 call every 2s
CALL_DELAY_S = 2.0
N_CALLS = 25  # 25 individual traces


def _run_sequential(client, n: int) -> list[CallResult]:
    """Run n calls sequentially with 2s delay (30 RPM)."""
    results = []
    for i in range(n):
        prompt = SYNTHETIC_PROMPTS[i % len(SYNTHETIC_PROMPTS)]
        trace_name = f"call_{i+1:03d}"
        result = individual_call(
            client,
            trace_name=trace_name,
            prompt=prompt,
            max_tokens=64,
            workflow="multiple_calls",
        )
        results.append(result)
        print(f"  [{i+1:02d}/{n}] {trace_name}  "
              f"in={result.usage_input:>3} out={result.usage_output:>3}  "
              f"dur={result.duration_s:.3f}s  "
              f"trace={result.trace_id[:16]}...")
        if i < n - 1:
            time.sleep(CALL_DELAY_S)
    return results


async def _run_concurrent(client, n: int, offset: int) -> list[CallResult]:
    """Run n calls concurrently (all at once, within rate limit)."""
    async def _one(idx: int) -> CallResult:
        prompt = SYNTHETIC_PROMPTS[idx % len(SYNTHETIC_PROMPTS)]
        trace_name = f"conc_call_{offset+idx+1:03d}"
        return await asyncio.to_thread(
            individual_call, client,
            trace_name=trace_name,
            prompt=prompt,
            max_tokens=64,
            workflow="multiple_calls_concurrent",
        )

    results = await asyncio.gather(*[_one(i) for i in range(n)])
    for i, r in enumerate(results):
        print(f"  [{i+1:02d}/{n}] conc_call_{offset+i+1:03d}  "
              f"in={r.usage_input:>3} out={r.usage_output:>3}  "
              f"dur={r.duration_s:.3f}s  "
              f"trace={r.trace_id[:16]}...")
    return results


def _percentiles(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(p / 100 * len(s)) - 1))
    return s[idx]


def _report(label: str, results: list[CallResult], wall: float) -> None:
    durs = [r.duration_s for r in results]
    total_in = sum(r.usage_input for r in results)
    total_out = sum(r.usage_output for r in results)
    total_usage = Usage(total_in, total_out, total_in + total_out)
    from observability.pricing import estimate_cost
    cost = estimate_cost(total_usage, model_name())
    errors = [r for r in results if r.error]

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  traces:          {len(results)} (each is an individual trace)")
    print(f"  wall time:       {wall:.3f}s")
    print(f"  throughput:      {len(results)/wall:.2f} traces/s" if wall else "")
    print(f"  latency p50:     {statistics.median(durs):.3f}s")
    print(f"  latency p95:     {_percentiles(durs, 95):.3f}s")
    print(f"  latency min:     {min(durs):.3f}s")
    print(f"  latency max:     {max(durs):.3f}s")
    print(f"  input tokens:    {total_in}")
    print(f"  output tokens:   {total_out}")
    print(f"  est. cost:       ~${cost.total_cost:.6f}" if cost else "  est. cost:       missing pricing")
    if errors:
        print(f"  errors:          {len(errors)}/{len(results)}")


def run_multiple() -> None:
    ensure_otel()
    model = model_name()
    allow_live = live_calls_allowed()

    print(f"{'='*60}")
    print(f"  MULTIPLE CALLS — {N_CALLS} individual traces")
    print(f"  Model: {model} | Live: {allow_live}")
    print(f"  Rate limit: 30 RPM (2s delay between sequential calls)")
    print(f"{'='*60}")

    if not allow_live:
        print("\n  [dry-run] Set ALLOW_LIVE_CALLS=1 for real API calls")
        print("  Each call would produce its own trace in Langfuse.")
        return

    client = make_groq_client()

    # --- Sequential (rate-limited) ---
    print(f"\n--- Sequential ({N_CALLS} traces, 2s delay) ---")
    seq_start = time.perf_counter()
    seq_results = _run_sequential(client, N_CALLS)
    seq_wall = time.perf_counter() - seq_start
    _report(f"SEQUENTIAL — {N_CALLS} individual traces", seq_results, seq_wall)

    # --- Concurrent (all at once) ---
    print(f"\n--- Concurrent ({N_CALLS} traces, all at once) ---")
    conc_start = time.perf_counter()
    conc_results = asyncio.run(_run_concurrent(client, N_CALLS, N_CALLS))
    conc_wall = time.perf_counter() - conc_start
    _report(f"CONCURRENT — {N_CALLS} individual traces", conc_results, conc_wall)

    # --- Summary ---
    total_traces = len(seq_results) + len(conc_results)
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Total individual traces: {total_traces}")
    print(f"  Sequential:              {len(seq_results)} traces in {seq_wall:.1f}s")
    print(f"  Concurrent:              {len(conc_results)} traces in {conc_wall:.1f}s")
    print(f"  Speedup:                 {seq_wall/conc_wall:.1f}x")
    print(f"\n  In Langfuse: {total_traces} separate trace rows, each with:")
    print(f"    - Clean Input (prompt text)")
    print(f"    - Clean Output (response text)")
    print(f"    - Cost, tokens, latency per trace")


if __name__ == "__main__":
    try:
        run_multiple()
    finally:
        with suppress(Exception):
            shutdown_all()
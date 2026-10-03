"""Script 5 — Batch of 30 individual traces for dashboard data.

Each call is its OWN trace — no parent workflow span.
30 individual traces in Langfuse, each with:
  - Clean Input (prompt text)
  - Clean Output (response text)
  - Cost per trace
  - Latency per trace
  - Token count per trace

15 sequential + 15 concurrent = 30 total individual traces.

Longer prompts with max_tokens=256 to generate varied output lengths
and realistic cost/latency distributions for dashboards.

Set ALLOW_LIVE_CALLS=1 in .env before running.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
from contextlib import suppress

from observability.instrumentation import configure_otel, shutdown_otel
from observability.metadata import build_attributes
from observability.usage import extract_usage, Usage, zero_usage
from observability.pricing import estimate_cost

from examples._common import individual_call, model_name

from dotenv import load_dotenv
load_dotenv()

# Longer, varied prompts to produce different output lengths and token counts.
BATCH_PROMPTS = [
    "Explain what observability means in software engineering in 3 sentences.",
    "List 5 best practices for monitoring LLM applications.",
    "Describe the difference between tracing and metrics in 2 sentences.",
    "What are OpenTelemetry semantic conventions? Answer in 3 sentences.",
    "Explain why token counting matters for LLM cost in 2 sentences.",
    "Name 4 popular LLM observability tools and what each one is best at.",
    "Describe what a trace waterfall is and why it's useful. 2-3 sentences.",
    "Explain p50 vs p95 latency and why p95 matters more for UX. 3 sentences.",
    "What is the difference between logs and traces? 2 sentences.",
    "Name 3 challenges of monitoring LLM applications vs traditional apps.",
    "Explain what a histogram is and how it's used for latency monitoring.",
    "What is an SLO and why is it important? 2-3 sentences.",
    "Describe what error budget means in reliability engineering. 2 sentences.",
    "List 4 key metrics every LLM application should track.",
    "Explain the concept of distributed tracing in 3 sentences.",
]

MAX_TOKENS = 256
N_SEQ = 15
N_CONC = 15
CALL_DELAY_S = 2.0  # 30 RPM rate limit for sequential


def _make_client():
    from groq import Groq
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def _run_sequential(client) -> list:
    """Run 15 calls sequentially with 2s delay."""
    results = []
    for i in range(N_SEQ):
        prompt = BATCH_PROMPTS[i % len(BATCH_PROMPTS)]
        trace_name = f"batch_seq_{i+1:03d}"
        result = individual_call(
            client,
            trace_name=trace_name,
            prompt=prompt,
            max_tokens=MAX_TOKENS,
            workflow="batch_sequential",
            user_id=f"user_{i % 5:02d}",
            session_id="batch_seq",
        )
        results.append(result)
        print(f"  [{i+1:02d}/{N_SEQ}] {trace_name}  "
              f"in={result.usage_input:>3} out={result.usage_output:>4}  "
              f"dur={result.duration_s:.3f}s  "
              f"${estimate_cost(Usage(result.usage_input, result.usage_output, result.usage_input+result.usage_output), model_name()).total_cost:.6f}" if result.error is None else f"  [{i+1:02d}/{N_SEQ}] {trace_name}  ERROR: {result.error}")
        if i < N_SEQ - 1:
            time.sleep(CALL_DELAY_S)
    return results


async def _run_concurrent(client) -> list:
    """Run 15 calls concurrently."""
    async def _one(idx: int):
        prompt = BATCH_PROMPTS[idx % len(BATCH_PROMPTS)]
        trace_name = f"batch_conc_{idx+1:03d}"
        return await asyncio.to_thread(
            individual_call, client,
            trace_name=trace_name,
            prompt=prompt,
            max_tokens=MAX_TOKENS,
            workflow="batch_concurrent",
            user_id=f"user_{idx % 5:02d}",
            session_id="batch_conc",
        )
    return await asyncio.gather(*[_one(i) for i in range(N_CONC)])


def _print_report(label: str, results: list, wall: float) -> None:
    durs = [r.duration_s for r in results]
    in_tok = sum(r.usage_input for r in results)
    out_tok = sum(r.usage_output for r in results)
    total_usage = Usage(in_tok, out_tok, in_tok + out_tok)
    cost = estimate_cost(total_usage, model_name())
    errors = [r for r in results if r.error]

    p50 = statistics.median(durs) if durs else 0
    p95_idx = max(0, min(len(durs) - 1, int(0.95 * len(durs)) - 1))
    p95 = sorted(durs)[p95_idx] if durs else 0

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  individual traces: {len(results)}")
    print(f"  wall time:         {wall:.3f}s")
    print(f"  throughput:        {len(results)/wall:.2f} traces/s" if wall else "")
    print(f"  latency p50:       {p50:.3f}s")
    print(f"  latency p95:       {p95:.3f}s")
    print(f"  input tokens:      {in_tok}")
    print(f"  output tokens:     {out_tok}")
    print(f"  total tokens:      {in_tok + out_tok}")
    print(f"  est. cost:         ~${cost.total_cost:.6f}" if cost else "  est. cost:         missing pricing")
    if errors:
        print(f"  errors:            {len(errors)}/{len(results)}")


def run_batch() -> None:
    configure_otel()
    from observability.metrics import configure_metrics
    configure_metrics()
    model = model_name()
    allow_live = os.getenv("ALLOW_LIVE_CALLS", "0") == "1"

    print(f"{'='*60}")
    print(f"  BATCH DASHBOARD — {N_SEQ + N_CONC} individual traces")
    print(f"  Model: {model} | Live: {allow_live}")
    print(f"  {N_SEQ} sequential (2s delay) + {N_CONC} concurrent")
    print(f"{'='*60}")

    if not allow_live:
        print("\n  [dry-run] Set ALLOW_LIVE_CALLS=1 for real API calls")
        return

    client = _make_client()

    # --- Sequential batch ---
    print(f"\n--- Sequential ({N_SEQ} individual traces) ---")
    seq_start = time.perf_counter()
    seq_results = _run_sequential(client)
    seq_wall = time.perf_counter() - seq_start
    _print_report(f"SEQUENTIAL — {N_SEQ} individual traces", seq_results, seq_wall)

    # --- Concurrent batch ---
    print(f"\n--- Concurrent ({N_CONC} individual traces) ---")
    conc_start = time.perf_counter()
    conc_results = asyncio.run(_run_concurrent(client))
    conc_wall = time.perf_counter() - conc_start
    _print_report(f"CONCURRENT — {N_CONC} individual traces", conc_results, conc_wall)

    # --- Grand total ---
    total = len(seq_results) + len(conc_results)
    total_in = sum(r.usage_input for r in seq_results + conc_results)
    total_out = sum(r.usage_output for r in seq_results + conc_results)
    total_cost = estimate_cost(Usage(total_in, total_out, total_in + total_out), model)

    print(f"\n{'='*60}")
    print(f"  GRAND TOTAL")
    print(f"{'='*60}")
    print(f"  total individual traces: {total}")
    print(f"  total input tokens:      {total_in}")
    print(f"  total output tokens:     {total_out}")
    print(f"  total est. cost:         ~${total_cost.total_cost:.6f}" if total_cost else "")
    print(f"  seq wall:                {seq_wall:.1f}s")
    print(f"  conc wall:               {conc_wall:.1f}s")
    print(f"\n  In Langfuse: {total} separate trace rows")
    print(f"  In Grafana: check Token & Cost + Service Overview dashboards")


if __name__ == "__main__":
    try:
        run_batch()
    finally:
        with suppress(Exception):
            from observability.metrics import flush_metrics, shutdown_metrics
            flush_metrics()
            shutdown_metrics()
            shutdown_otel()
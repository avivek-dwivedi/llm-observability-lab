"""Script 7 — LLM Evaluation: 5 individual traces with full input/output + scores.

Each evaluation case is its OWN trace in Langfuse:
  - Trace name: eval.<case_name>
  - Clean Input (prompt text)
  - Clean Output (response text)
  - Scores as span attributes (langfuse.score.*.value)
  - Scores visible in Langfuse Scores column + Scores dashboard

5 test cases with known prompts and expected keywords.
4 heuristic checks per case:
  - success:      did the call complete without error?
  - relevance:   does the response contain expected keywords?
  - completeness: is the response non-empty and non-trivial?
  - conciseness:  is the response within a reasonable token budget?

Set ALLOW_LIVE_CALLS=1 in .env (needs real Groq calls).
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import suppress
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from observability.instrumentation import configure_otel, completions_span, shutdown_otel
from observability.metrics import configure_metrics, flush_metrics, shutdown_metrics
from observability.usage import extract_usage, zero_usage
from observability.pricing import estimate_cost
from observability.metadata import build_attributes

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# ---------------------------------------------------------------------------
# Evaluation test cases
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    name: str
    prompt: str
    expected_keywords: list[str]
    max_output_tokens: int = 128


EVAL_CASES: list[EvalCase] = [
    EvalCase(
        name="primary_colors",
        prompt="List three primary colors.",
        expected_keywords=["red", "blue", "yellow"],
    ),
    EvalCase(
        name="chemical_symbol_water",
        prompt="What is the chemical symbol for water?",
        expected_keywords=["h2o", "h₂o"],
    ),
    EvalCase(
        name="simple_math",
        prompt="What is 2 + 2? Answer with just the number.",
        expected_keywords=["4"],
        max_output_tokens=16,
    ),
    EvalCase(
        name="planet_name",
        prompt="Name a planet in our solar system.",
        expected_keywords=["mercury", "venus", "earth", "mars", "jupiter",
                           "saturn", "uranus", "neptune"],
    ),
    EvalCase(
        name="programming_language",
        prompt="Name a programming language.",
        expected_keywords=["python", "java", "javascript", "c++", "go",
                           "rust", "ruby", "kotlin", "swift", "typescript"],
    ),
]


# ---------------------------------------------------------------------------
# Heuristic evaluators
# ---------------------------------------------------------------------------

@dataclass
class EvalScore:
    name: str
    value: float
    comment: str


def eval_completeness(answer: str) -> EvalScore:
    if not answer or len(answer.strip()) == 0:
        return EvalScore("completeness", 0.0, "empty response")
    stripped = answer.strip()
    if len(stripped) < 2:
        return EvalScore("completeness", 0.5, f"very short: '{stripped}'")
    return EvalScore("completeness", 1.0, f"response length={len(answer)} chars")


def eval_relevance(answer: str, expected_keywords: list[str]) -> EvalScore:
    answer_lower = answer.lower()
    matched = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    if not expected_keywords:
        return EvalScore("relevance", 1.0, "no keywords to check")
    if matched:
        return EvalScore("relevance", 1.0, f"matched: {', '.join(matched)}")
    return EvalScore("relevance", 0.0, f"none of {expected_keywords} found")


def eval_conciseness(output_tokens: int, limit: int = 256) -> EvalScore:
    if output_tokens == 0:
        return EvalScore("conciseness", 0.0, "no output tokens")
    if output_tokens <= limit:
        return EvalScore("conciseness", 1.0, f"{output_tokens} tokens (limit {limit})")
    return EvalScore("conciseness", 0.5, f"{output_tokens} tokens exceeds limit {limit}")


def eval_success(error: str | None) -> EvalScore:
    if error:
        return EvalScore("success", 0.0, f"error: {error}")
    return EvalScore("success", 1.0, "completed successfully")


# ---------------------------------------------------------------------------
# Run one evaluation case as its own individual trace
# ---------------------------------------------------------------------------

def _run_eval_case(client, case: EvalCase, model: str, allow_live: bool) -> dict:
    """Run one eval case as a standalone trace with scores."""
    trace_name = f"eval.{case.name}"
    error = None
    answer = ""
    usage = zero_usage()
    duration_s = 0.0

    with completions_span(
        name=trace_name,
        model=model,
        prompt=case.prompt,
        max_tokens=case.max_output_tokens,
        extra_attributes={"eval.case": case.name},
    ) as span:
        start = time.perf_counter()
        try:
            if allow_live and client:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": case.prompt}],
                    max_tokens=case.max_output_tokens,
                    temperature=0.0,
                )
                usage = extract_usage(resp)
                answer = resp.choices[0].message.content or ""
                import json
                span.set_attribute("llm.output_messages",
                    json.dumps([{"role": "assistant", "content": answer}], ensure_ascii=False))
                span.set_attribute("gen_ai.completion", answer)
                span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
                span.set_attribute("llm.token_count.prompt", usage.input_tokens)
                span.set_attribute("llm.token_count.completion", usage.output_tokens)
                span.set_attribute("llm.token_count.total", usage.total_tokens)
                cost = estimate_cost(usage, model)
                if cost:
                    span.set_attribute("cost.estimated_usd", cost.total_cost)
            else:
                canned = {
                    "primary_colors": "Red, blue, and yellow.",
                    "chemical_symbol_water": "H2O",
                    "simple_math": "4",
                    "planet_name": "Earth",
                    "programming_language": "Python",
                }
                answer = canned.get(case.name, "(dry-run)")
                usage = zero_usage()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))

        duration_s = time.perf_counter() - start
        span.set_attribute("eval.duration_s", round(duration_s, 6))

        # Run evaluators
        scores = [
            eval_success(error),
            eval_completeness(answer),
            eval_relevance(answer, case.expected_keywords),
            eval_conciseness(usage.output_tokens),
        ]

        # Attach scores to span → Langfuse renders them in Scores column
        for s in scores:
            span.set_attribute(f"langfuse.score.{s.name}.value", s.value)
            span.set_attribute(f"langfuse.score.{s.name}.comment", s.comment)
            span.set_attribute(f"eval.{s.name}", s.value)

        # Also record metrics for Grafana
        from examples._common import record_call_metrics, CallResult
        result = CallResult(
            text=answer, usage_input=usage.input_tokens, usage_output=usage.output_tokens,
            duration_s=duration_s, model=model, trace_id="", span_id="", error=error,
        )
        record_call_metrics(result, workflow=trace_name)

    # Print results
    avg = sum(s.value for s in scores) / len(scores) if scores else 0
    print(f"\n  [{trace_name}]")
    print(f"    Prompt:   {case.prompt}")
    print(f"    Response: {answer[:80]}")
    for s in scores:
        icon = "✅" if s.value >= 1.0 else ("⚠️" if s.value > 0 else "❌")
        print(f"    {icon} {s.name:<15} {s.value:.1f}  {s.comment}")
    print(f"    → Overall: {avg:.1%}")

    return {
        "case": case.name,
        "trace_name": trace_name,
        "overall": avg,
        "scores": {s.name: s.value for s in scores},
        "answer": answer[:100],
        "error": error,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_evaluation() -> None:
    configure_otel()
    configure_metrics()

    model = os.getenv("GROQ_MODEL", "allam-2-7b")
    allow_live = os.getenv("ALLOW_LIVE_CALLS", "0") == "1"

    print(f"{'='*60}")
    print(f"  LLM EVALUATION — {len(EVAL_CASES)} individual traces")
    print(f"  Model: {model} | Live: {allow_live}")
    print(f"  Each case is its own trace with full input/output + scores")
    print(f"{'='*60}")

    client = None
    if allow_live:
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])

    all_scores = []
    for i, case in enumerate(EVAL_CASES):
        print(f"\n  [{i+1}/{len(EVAL_CASES)}]", end="")
        result = _run_eval_case(client, case, model, allow_live)
        all_scores.append(result)

    # Summary
    print(f"\n{'='*60}")
    print(f"  EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Trace':<30} {'Overall':>8} {'Success':>8} {'Relevant':>9} {'Complete':>9} {'Concise':>8}")
    print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*9} {'-'*9} {'-'*8}")

    for r in all_scores:
        s = r["scores"]
        print(f"  {r['trace_name']:<30} {r['overall']:>7.0%} "
              f"{s.get('success',0):>7.0%} {s.get('relevance',0):>8.0%} "
              f"{s.get('completeness',0):>8.0%} {s.get('conciseness',0):>7.0%}")

    overall_avg = sum(r["overall"] for r in all_scores) / len(all_scores) if all_scores else 0
    print()
    print(f"  Total traces:     {len(all_scores)}")
    print(f"  Average score:    {overall_avg:.1%}")
    print()
    print(f"  In Langfuse: {len(all_scores)} separate trace rows (eval.*)")
    print(f"  Each trace shows: Input, Output, Scores in Scores column")
    print(f"  Scores dashboard: check langfuse.score.* attributes")


if __name__ == "__main__":
    try:
        run_evaluation()
    finally:
        with suppress(Exception):
            flush_metrics()
            shutdown_metrics()
            shutdown_otel()
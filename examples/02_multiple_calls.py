"""Script 2 — Nested pipeline: RAG / Agent style.

ONE trace with nested child spans — simulates a real agent workflow:

    rag_pipeline (root trace)
    ├── retrieve_context    (child — fetches relevant context)
    │   └── Completions     (grandchild — LLM generates search query)
    ├── generate_answer     (child — LLM answers using context)
    │   └── Completions     (grandchild — the actual LLM call with input/output)
    └── evaluate_answer     (child — checks answer quality)
        └── Completions     (grandchild — LLM self-evaluation)

The root trace row in Langfuse shows:
  - Name: rag_pipeline
  - Total trace time (sum of all children)
  - Input/Output at each child level
  - Token counts aggregated

This is the ONLY script that uses nested children — because a RAG pipeline
IS a multi-step workflow that belongs in one trace.
"""

from __future__ import annotations

import time
from contextlib import suppress

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from observability.instrumentation import workflow_span, completions_span
from observability.metadata import build_attributes
from observability.usage import extract_usage, zero_usage
from observability.pricing import estimate_cost

from examples._common import (
    ensure_otel,
    live_calls_allowed,
    make_groq_client,
    model_name,
    shutdown_all,
    record_call_metrics,
    CallResult,
)


def _llm_call(client, *, span_name: str, prompt: str, max_tokens: int = 128,
              workflow: str = "") -> tuple[str, object, str | None]:
    """One LLM call wrapped in a Completions child span.

    Returns (text, usage, error).
    """
    model = model_name()
    usage = zero_usage()
    text = ""
    error: str | None = None

    with completions_span(
        name=span_name,
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
    ) as span:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.0,
            )
            usage = extract_usage(resp)
            text = resp.choices[0].message.content or ""
            import json
            span.set_attribute("llm.output_messages",
                json.dumps([{"role": "assistant", "content": text}], ensure_ascii=False))
            span.set_attribute("gen_ai.completion", text)
            span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            span.set_attribute("llm.token_count.prompt", usage.input_tokens)
            span.set_attribute("llm.token_count.completion", usage.output_tokens)
            span.set_attribute("llm.token_count.total", usage.total_tokens)
            cost = estimate_cost(usage, model)
            if cost:
                span.set_attribute("cost.estimated_usd", cost.total_cost)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))

    # Record metrics
    result = CallResult(
        text=text, usage_input=usage.input_tokens, usage_output=usage.output_tokens,
        duration_s=0.0, model=model, trace_id="", span_id="", error=error,
    )
    record_call_metrics(result, workflow=workflow)

    return text, usage, error


def run_rag_pipeline() -> None:
    """Run a simulated RAG pipeline as ONE trace with nested children."""
    ensure_otel()
    model = model_name()
    allow_live = live_calls_allowed()

    print(f"{'='*60}")
    print(f"  RAG PIPELINE — Nested trace (1 trace, 3 child stages)")
    print(f"  Model: {model} | Live: {allow_live}")
    print(f"{'='*60}")

    # The root trace — everything inside is a child of this span
    with workflow_span(
        "rag_pipeline",
        attributes=build_attributes(
            model=model, operation="workflow",
            extra={"pipeline.type": "rag", "pipeline.stages": "retrieve,generate,evaluate"},
        ),
    ) as root:
        client = make_groq_client() if allow_live else None
        pipeline_start = time.perf_counter()

        # --- Stage 1: Retrieve context ---
        print("\n  [1/3] retrieve_context")
        with workflow_span(
            "retrieve_context",
            attributes=build_attributes(model=model, operation="retrieve",
                                        extra={"stage": "retrieve"}),
        ) as retrieve_span:
            retrieve_query = "What is observability in software engineering?"
            retrieve_prompt = f"Generate a search query to find documentation about: {retrieve_query}"

            if allow_live and client:
                text, usage, err = _llm_call(
                    client, span_name="Completions", prompt=retrieve_prompt,
                    max_tokens=64, workflow="rag_pipeline.retrieve",
                )
                retrieved_context = text
                retrieve_span.set_attribute("retrieve.query", retrieve_query)
                retrieve_span.set_attribute("retrieve.context_length", len(text))
                print(f"        query: {retrieve_query}")
                print(f"        retrieved: {text[:80]}...")
            else:
                retrieved_context = "Observability is the ability to understand a system's internal state from its external outputs."
                retrieve_span.set_attribute("retrieve.query", retrieve_query)
                retrieve_span.set_attribute("retrieve.context_length", len(retrieved_context))
                print(f"        [dry-run] retrieved_context = '{retrieved_context[:60]}...'")

        # --- Stage 2: Generate answer using context ---
        print("\n  [2/3] generate_answer")
        with workflow_span(
            "generate_answer",
            attributes=build_attributes(model=model, operation="generate",
                                        extra={"stage": "generate"}),
        ) as generate_span:
            gen_prompt = (
                f"Context: {retrieved_context}\n\n"
                f"Question: {retrieve_query}\n"
                f"Answer the question using the context above in 2-3 sentences."
            )
            generate_span.set_attribute("generate.context", retrieved_context[:200])
            generate_span.set_attribute("generate.question", retrieve_query)

            if allow_live and client:
                text, usage, err = _llm_call(
                    client, span_name="Completions", prompt=gen_prompt,
                    max_tokens=256, workflow="rag_pipeline.generate",
                )
                answer = text
                generate_span.set_attribute("generate.answer_length", len(answer))
                print(f"        answer: {answer[:100]}...")
            else:
                answer = "[dry-run] Observability means understanding a system's state from its outputs."
                print(f"        [dry-run] answer = '{answer[:60]}...'")

        # --- Stage 3: Evaluate the answer ---
        print("\n  [3/3] evaluate_answer")
        with workflow_span(
            "evaluate_answer",
            attributes=build_attributes(model=model, operation="evaluate",
                                        extra={"stage": "evaluate"}),
        ) as eval_span:
            eval_prompt = (
                f"Question: {retrieve_query}\n"
                f"Answer: {answer}\n\n"
                f"Is this answer accurate and complete? Rate it 1-10 and explain briefly."
            )

            if allow_live and client:
                text, usage, err = _llm_call(
                    client, span_name="Completions", prompt=eval_prompt,
                    max_tokens=128, workflow="rag_pipeline.evaluate",
                )
                evaluation = text
                eval_span.set_attribute("evaluate.response", evaluation[:200])
                print(f"        evaluation: {evaluation[:100]}...")
            else:
                evaluation = "[dry-run] Score: 8/10. The answer is accurate but could be more detailed."
                print(f"        [dry-run] {evaluation}")

        # --- Root span summary ---
        total_dur = time.perf_counter() - pipeline_start
        root.set_attributes({
            "pipeline.total_duration_s": round(total_dur, 3),
            "pipeline.stages_completed": 3,
            "pipeline.retrieved_context": retrieved_context[:200],
            "pipeline.final_answer": answer[:200],
            "pipeline.evaluation": evaluation[:200],
        })

        ctx = root.get_span_context()
        print(f"\n  {'='*56}")
        print(f"  PIPELINE COMPLETE")
        print(f"  {'='*56}")
        print(f"  Total duration:   {total_dur:.3f}s")
        print(f"  Stages:           3 (retrieve -> generate -> evaluate)")
        print(f"  Trace ID:         {ctx.trace_id:032x}")
        print(f"  Span ID:          {ctx.span_id:016x}")
        print(f"\n  In Langfuse: look for trace 'rag_pipeline'")
        print(f"  Click it -> expand -> see 3 child stages, each with Completions")


if __name__ == "__main__":
    try:
        run_rag_pipeline()
    finally:
        with suppress(Exception):
            shutdown_all()
"""Shared helpers for the example scripts.

- Loads `.env` once.
- Initialises the single OTel pipeline.
- Provides a controlled Groq client + a fake provider for failure scripts.
- Guards live calls behind ``ALLOW_LIVE_CALLS``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# --- observability -----------------------------------------------------------
from observability.instrumentation import configure_otel, shutdown_otel  # noqa: E402

CONFIGURED = False


def ensure_otel() -> None:
    global CONFIGURED
    if not CONFIGURED:
        configure_otel()
        # V2: also configure metrics (safe to call multiple times)
        from observability.metrics import configure_metrics
        configure_metrics()
        CONFIGURED = True


def live_calls_allowed() -> bool:
    return os.getenv("ALLOW_LIVE_CALLS", "0") == "1"


def model_name() -> str:
    return os.getenv("GROQ_MODEL", "allam-2-7b")


# --- Groq client (real) ------------------------------------------------------
def make_groq_client():  # pragma: no cover - needs network + key
    from groq import Groq

    ensure_otel()
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def groq_chat(client, *, prompt: str, max_tokens: int = 64, temperature: float = 0.0):
    """One chat completion. Prompt text is NOT recorded anywhere."""
    return client.chat.completions.create(
        model=model_name(),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )


def groq_chat_traced(client, *, prompt: str, max_tokens: int = 64, temperature: float = 0.0,
                     user_id: str = "", session_id: str = ""):
    """One chat completion wrapped in a clean Completions span.

    Creates a manual Completions child span with clean llm.input_messages /
    llm.output_messages JSON — no groq.Omit objects.  Returns (response, usage, text, error).
    """
    from observability.instrumentation import completions_span
    from observability.usage import extract_usage, zero_usage
    from observability.metadata import build_attributes

    model = model_name()
    error: str | None = None
    resp = None
    usage = zero_usage()
    text = ""

    with completions_span(
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        user_id=user_id,
        session_id=session_id,
    ) as span:
        import time as _time
        start = _time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            usage = extract_usage(resp)
            text = resp.choices[0].message.content or ""
            # Set output and token attributes on the span
            import json as _json
            span.set_attribute("llm.output_messages",
                               _json.dumps([{"role": "assistant", "content": text}], ensure_ascii=False))
            span.set_attribute("gen_ai.completion", text)
            span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            span.set_attribute("llm.token_count.prompt", usage.input_tokens)
            span.set_attribute("llm.token_count.completion", usage.output_tokens)
            span.set_attribute("llm.token_count.total", usage.total_tokens)
            span.set_attribute("gen_ai.response.model", model)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            span.record_exception(exc)
            from opentelemetry.trace import Status, StatusCode
            span.set_status(Status(StatusCode.ERROR, str(exc)))
        dur = _time.perf_counter() - start
        span.set_attribute("gen_ai.response.duration_s", round(dur, 6))

    return resp, usage, text, error


def individual_call(
    client,
    *,
    trace_name: str,
    prompt: str,
    max_tokens: int = 64,
    temperature: float = 0.0,
    workflow: str = "",
    user_id: str = "",
    session_id: str = "",
) -> CallResult:
    """Make one Groq call as a STANDALONE trace.

    Each call produces its own root trace (no parent workflow span).
    The trace name is visible in Langfuse's Tracing list as a separate row.
    Records V2 metrics (requests, tokens, cost, latency) for Grafana.

    Returns a CallResult with trace_id so you can find it in the UIs.
    """
    import time as _time
    import json as _json
    from opentelemetry import trace as _trace
    from observability.instrumentation import completions_span
    from observability.usage import extract_usage, zero_usage
    from observability.pricing import estimate_cost

    model = model_name()
    error: str | None = None
    usage = zero_usage()
    text = ""

    # Each call is a root trace — the Completions span IS the root span.
    # Its name appears as the trace name in Langfuse.
    with completions_span(
        name=trace_name,
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        user_id=user_id,
        session_id=session_id,
    ) as span:
        start = _time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            usage = extract_usage(resp)
            text = resp.choices[0].message.content or ""
            span.set_attribute("llm.output_messages",
                               _json.dumps([{"role": "assistant", "content": text}], ensure_ascii=False))
            span.set_attribute("gen_ai.completion", text)
            span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            span.set_attribute("llm.token_count.prompt", usage.input_tokens)
            span.set_attribute("llm.token_count.completion", usage.output_tokens)
            span.set_attribute("llm.token_count.total", usage.total_tokens)
            span.set_attribute("gen_ai.response.model", model)
            cost = estimate_cost(usage, model)
            if cost:
                span.set_attribute("cost.estimated_usd", cost.total_cost)
                span.set_attribute("cost.source", cost.source)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            span.record_exception(exc)
            from opentelemetry.trace import Status, StatusCode
            span.set_status(Status(StatusCode.ERROR, str(exc)))
        dur = _time.perf_counter() - start
        span.set_attribute("gen_ai.response.duration_s", round(dur, 6))

    ctx = span.get_span_context()
    result = CallResult(
        text=text,
        usage_input=usage.input_tokens,
        usage_output=usage.output_tokens,
        duration_s=dur,
        model=model,
        trace_id=f"{ctx.trace_id:032x}",
        span_id=f"{ctx.span_id:016x}",
        error=error,
    )

    # Record V2 metrics for Grafana
    record_call_metrics(result, workflow=workflow or trace_name)

    return result


# --- Synthetic prompts (no secrets, deterministic) ---------------------------
SYNTHETIC_PROMPTS = [
    "List three primary colors.",
    "Name a planet in our solar system.",
    "Give a one-word antonym for 'hot'.",
    "What is 2 + 2? Answer with just the number.",
    "Name a programming language.",
    "What is the chemical symbol for water?",
    "Name a day of the week.",
    "Give a one-word synonym for 'fast'.",
    "What is the capital of France? One word.",
    "Name a musical instrument.",
    "What color is the sky on a clear day?",
    "Name a type of tree.",
    "What is 5 minus 3? Just the number.",
    "Name a mode of transportation.",
    "What is the opposite of 'day'?",
    "Name a common household pet.",
    "What language is spoken in Japan? One word.",
    "Name a primary color that starts with 'b'.",
    "What is the largest ocean? One word.",
    "Name a type of weather.",
    "What is 10 divided by 2? Just the number.",
    "Name a winter sport.",
    "What is the boiling point of water in Celsius? Just the number.",
    "Name a green vegetable.",
    "What is the square root of 9? Just the number.",
    "Name a continent that starts with 'A'.",
    "What gas do plants absorb? One word.",
    "Name a famous scientist.",
    "What is 3 multiplied by 4? Just the number.",
    "Name a piece of furniture.",
]


@dataclass
class CallResult:
    text: str
    usage_input: int
    usage_output: int
    duration_s: float
    model: str
    trace_id: str
    span_id: str
    error: str | None = None


def summarise(result: CallResult) -> str:
    err = f" error={result.error}" if result.error else ""
    return (
        f"[{result.model}] in={result.usage_input} out={result.usage_output} "
        f"dur={result.duration_s:.3f}s trace={result.trace_id} "
        f"span={result.span_id}{err}"
    )


def record_call_metrics(result: CallResult, workflow: str = "") -> None:
    """Record V2 metrics for a single call result."""
    from observability.metrics import (
        record_request,
        record_tokens,
        record_cost,
        record_duration,
    )
    from observability.pricing import estimate_cost
    from observability.usage import Usage

    is_success = result.error is None
    result_label = "success" if is_success else "error"
    model = result.model

    record_request(model=model, workflow=workflow, result=result_label)
    if is_success and (result.usage_input > 0 or result.usage_output > 0):
        record_tokens(
            input_tokens=result.usage_input,
            output_tokens=result.usage_output,
            model=model,
            workflow=workflow,
        )
        usage = Usage(
            input_tokens=result.usage_input,
            output_tokens=result.usage_output,
            total_tokens=result.usage_input + result.usage_output,
        )
        cost = estimate_cost(usage, model)
        if cost:
            record_cost(cost_usd=cost.total_cost, model=model, workflow=workflow)
    record_duration(
        duration_s=result.duration_s,
        model=model,
        workflow=workflow,
        result=result_label,
    )


def shutdown_all() -> None:
    """Flush and shut down both traces and metrics. Call before exit."""
    from contextlib import suppress
    with suppress(Exception):
        from observability.metrics import flush_metrics, shutdown_metrics
        flush_metrics()
        shutdown_metrics()
    with suppress(Exception):
        shutdown_otel()


def post_langfuse_score(
    *,
    trace_id: str,
    name: str,
    value: float,
    comment: str = "",
) -> bool:
    """POST one native Score object to Langfuse for an existing trace.

    Span attributes (``langfuse.score.*``) show up in the trace detail view,
    but Langfuse only counts native **Score objects** in the Scores dashboard
    / Usage Management 'Total Score Count' panels.  This helper posts the
    score via ``POST /api/public/scores``.

    Args:
        trace_id: 32-hex OTel trace id (CallResult.trace_id) — Langfuse's
            OTel ingestion maps these 1:1 to its trace ids.
        name: score name, e.g. "relevance".
        value: numeric score value.
        comment: optional human-readable feedback.

    Returns True if the score was accepted (201), False otherwise.
    Failures are non-fatal: evaluation continues without scores.
    """
    import base64
    import json
    import urllib.error
    import urllib.request

    host = os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000").rstrip("/")
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not (pk and sk) or not trace_id:
        return False

    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    body = json.dumps({
        "id": __import__("uuid").uuid4().hex,
        "name": name,
        "traceId": trace_id,
        "value": value,
        "dataType": "NUMERIC",
        "source": "API",
        "environment": "default",
        "comment": comment or None,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{host}/api/public/scores",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 201
    except urllib.error.HTTPError as e:
        # 200 on update-by-id; anything else is a hard failure for this score.
        return e.code in (200,)
    except Exception:
        return False
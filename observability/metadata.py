"""Build standard span attributes for manual spans.

We capture the standard GenAI semantic conventions plus the OpenInference
attributes that the automatic Groq instrumentation does not already emit for
workflow/retry spans.  We never put prompt text, API keys or other secrets into
attributes.
"""

from __future__ import annotations

from opentelemetry.trace import Span
from observability.usage import Usage


# GenAI semantic-convention attribute names (kept as plain strings to avoid a
# hard dependency on the experimental sem-conv package).
GENAI_SYSTEM = "gen_ai.system"
GENAI_OPERATION = "gen_ai.operation.name"
GENAI_REQUEST_MODEL = "gen_ai.request.model"
GENAI_RESPONSE_MODEL = "gen_ai.response.model"
GENAI_USAGE_INPUT = "gen_ai.usage.input_tokens"
GENAI_USAGE_OUTPUT = "gen_ai.usage.output_tokens"
GENAI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GENAI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"

# OpenInference attributes
OPENINFERENCE_SPAN_KIND = "openinference.span.kind"
OPENINFERENCE_LLM_MODEL = "llm.model_name"
OPENINFERENCE_LLM_TOKEN_COUNT_TOTAL = "llm.token_count.total"
OPENINFERENCE_LLM_TOKEN_COUNT_PROMPT = "llm.token_count.prompt"
OPENINFERENCE_LLM_TOKEN_COUNT_COMPLETION = "llm.token_count.completion"


def build_attributes(
    *,
    model: str,
    provider: str = "groq",
    operation: str = "chat",
    usage: Usage | None = None,
    extra: dict | None = None,
) -> dict:
    """Assemble a flat attribute dict for a manual span."""
    attrs: dict = {
        GENAI_SYSTEM: provider,
        GENAI_OPERATION: operation,
        GENAI_REQUEST_MODEL: model,
        OPENINFERENCE_SPAN_KIND: "LLM",
        OPENINFERENCE_LLM_MODEL: model,
    }
    if usage is not None:
        attrs[GENAI_USAGE_INPUT] = usage.input_tokens
        attrs[GENAI_USAGE_OUTPUT] = usage.output_tokens
        attrs[OPENINFERENCE_LLM_TOKEN_COUNT_PROMPT] = usage.input_tokens
        attrs[OPENINFERENCE_LLM_TOKEN_COUNT_COMPLETION] = usage.output_tokens
        attrs[OPENINFERENCE_LLM_TOKEN_COUNT_TOTAL] = usage.total_tokens
    if extra:
        attrs.update(extra)
    return attrs


def set_span_attributes(span: Span, attrs: dict) -> None:
    """Set attributes on a span, skipping ``None`` values."""
    for key, value in attrs.items():
        if value is not None:
            span.set_attribute(key, value)
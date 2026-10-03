"""Tests for metadata attribute building."""

from observability.metadata import build_attributes, set_span_attributes
from observability.usage import Usage


def test_build_attributes_basic():
    attrs = build_attributes(model="allam-2-7b")
    assert attrs["gen_ai.system"] == "groq"
    assert attrs["gen_ai.request.model"] == "allam-2-7b"
    assert attrs["openinference.span.kind"] == "LLM"
    assert attrs["llm.model_name"] == "allam-2-7b"


def test_build_attributes_with_usage_sets_both_schemas():
    u = Usage(input_tokens=10, output_tokens=20, total_tokens=30)
    attrs = build_attributes(model="allam-2-7b", usage=u)
    # GenAI
    assert attrs["gen_ai.usage.input_tokens"] == 10
    assert attrs["gen_ai.usage.output_tokens"] == 20
    # OpenInference (must match so Phoenix + Langfuse/LangSmith agree)
    assert attrs["llm.token_count.prompt"] == 10
    assert attrs["llm.token_count.completion"] == 20
    assert attrs["llm.token_count.total"] == 30


def test_build_attributes_extra():
    attrs = build_attributes(model="m", extra={"workflow.kind": "demo"})
    assert attrs["workflow.kind"] == "demo"


def test_set_span_attributes_skips_none():
    class FakeSpan:
        def __init__(self):
            self.attrs = {}

        def set_attribute(self, k, v):
            self.attrs[k] = v

    s = FakeSpan()
    set_span_attributes(s, {"a": 1, "b": None, "c": "x"})
    assert s.attrs == {"a": 1, "c": "x"}
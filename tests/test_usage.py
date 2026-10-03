"""Tests for usage extraction from Groq-style responses."""

from types import SimpleNamespace

from observability.usage import extract_usage, zero_usage


def _resp(**kw):
    usage = SimpleNamespace(**kw)
    return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])


def test_extract_usage_full():
    resp = _resp(
        prompt_tokens=12,
        completion_tokens=34,
        total_tokens=46,
        prompt_time=0.01,
        completion_time=0.03,
        total_time=0.04,
    )
    u = extract_usage(resp)
    assert u.input_tokens == 12
    assert u.output_tokens == 34
    assert u.total_tokens == 46
    assert u.prompt_time_s == 0.01
    assert u.completion_time_s == 0.03
    assert u.total_time_s == 0.04


def test_extract_usage_dict():
    resp = {"usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}}
    u = extract_usage(resp)
    assert u.input_tokens == 5
    assert u.output_tokens == 7
    assert u.total_tokens == 12
    assert u.prompt_time_s is None


def test_extract_usage_missing():
    assert extract_usage(SimpleNamespace(usage=None)) == zero_usage()
    assert extract_usage({}) == zero_usage()


def test_zero_usage():
    z = zero_usage()
    assert (z.input_tokens, z.output_tokens, z.total_tokens) == (0, 0, 0)
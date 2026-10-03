"""Extract provider-reported token usage from Groq responses.

Groq (OpenAI-compatible) returns a ``usage`` dict on chat completions::

    {
        "prompt_tokens": 12,
        "completion_tokens": 34,
        "total_tokens": 46,
        "prompt_time": 0.01,
        "completion_time": 0.03,
        "total_time": 0.04
    }

We normalise it into a small dataclass so the rest of the lab does not have to
poke at dict keys.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    prompt_time_s: float | None = None
    completion_time_s: float | None = None
    total_time_s: float | None = None


def zero_usage() -> Usage:
    return Usage(0, 0, 0)


def extract_usage(response: object) -> Usage:
    """Pull ``usage`` out of a Groq ``ChatCompletion`` (or dict-like object)."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    if not usage:
        return zero_usage()

    def _get(key: str, default: int = 0) -> int:
        val = getattr(usage, key, None)
        if val is None and isinstance(usage, dict):
            val = usage.get(key)
        try:
            return int(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    def _get_float(key: str) -> float | None:
        val = getattr(usage, key, None)
        if val is None and isinstance(usage, dict):
            val = usage.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    return Usage(
        input_tokens=_get("prompt_tokens"),
        output_tokens=_get("completion_tokens"),
        total_tokens=_get("total_tokens"),
        prompt_time_s=_get_float("prompt_time"),
        completion_time_s=_get_float("completion_time"),
        total_time_s=_get_float("total_time"),
    )
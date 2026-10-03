"""Tests for the failure-scenario fake provider (no network).

The failure script lives at ``examples/04_failures.py`` which is not importable
as a module (leading digit), so we load it by path and assert the deterministic
fake-call contract without touching the network.
"""

import importlib.util
import pathlib

import pytest

from examples._common import SYNTHETIC_PROMPTS


def _load_failures_module():
    spec = importlib.util.spec_from_file_location(
        "example_04_failures",
        pathlib.Path(__file__).resolve().parent.parent
        / "examples"
        / "04_failures.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_synthetic_prompts_no_secrets():
    for p in SYNTHETIC_PROMPTS:
        assert isinstance(p, str) and len(p) < 80
        low = p.lower()
        assert "key" not in low and "token" not in low and "password" not in low


def test_fake_timeout():
    fx = _load_failures_module()
    with pytest.raises(fx.FakeTimeoutError):
        fx._fake_call("timeout", attempt=1)


def test_fake_rate_limit():
    fx = _load_failures_module()
    with pytest.raises(fx.FakeRateLimitError):
        fx._fake_call("rate_limit", attempt=1)


def test_fake_transient_then_success():
    fx = _load_failures_module()
    with pytest.raises(fx.FakeServerError):
        fx._fake_call("transient", attempt=1)
    # attempt=2 is NOT < 2, so it succeeds (the code uses `attempt < 2`)
    result = fx._fake_call("transient", attempt=2)
    assert "ok" in result.lower()
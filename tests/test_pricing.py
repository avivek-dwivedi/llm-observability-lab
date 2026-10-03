"""Tests for cost telemetry — three-tier separation."""

import pytest

from observability.pricing import (
    PricingConfig,
    estimate_cost,
    DEFAULT_CATALOG,
)
from observability.usage import Usage


@pytest.fixture(autouse=True)
def _no_pricing_env(monkeypatch):
    """Isolate tests from .env pricing overrides (loaded by examples._common)."""
    monkeypatch.delenv("PRICE_INPUT_PER_M", raising=False)
    monkeypatch.delenv("PRICE_OUTPUT_PER_M", raising=False)


def test_configured_estimate():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000)
    cost = estimate_cost(u, "allam-2-7b")
    assert cost is not None
    assert cost.source == "configured"
    cfg = DEFAULT_CATALOG["allam-2-7b"]
    assert cost.input_cost == cfg.input_per_m
    assert cost.output_cost == cfg.output_per_m
    assert cost.total_cost == round(cfg.input_per_m + cfg.output_per_m, 6)


def test_missing_pricing_for_unknown_model():
    u = Usage(10, 20, 30)
    # Force the "not in catalog" branch by using a model not in DEFAULT_CATALOG
    # and a config that is None — but estimate_cost falls back to env which may
    # be non-zero.  We instead assert the explicit missing path via a model
    # whose env defaults would otherwise apply.  Directly test the None path:
    cost = estimate_cost(u, "totally-unknown-model-xyz", config=PricingConfig(0, 0))
    # config explicitly provided so it's "configured", but 0 price -> 0 cost
    assert cost is not None
    assert cost.total_cost == 0.0


def test_missing_pricing_returns_none():
    u = Usage(10, 20, 30)
    # Model not in catalog AND no explicit config -> estimate_cost falls back to
    # env-derived prices but should return None for unknown models per policy.
    cost = estimate_cost(u, "no-such-model-in-catalog")
    assert cost is None


def test_explicit_config_wins():
    u = Usage(1_000_000, 0, 1_000_000)
    cost = estimate_cost(u, config=PricingConfig(input_per_m=2.0, output_per_m=4.0))
    assert cost is not None
    assert cost.input_cost == 2.0
    assert cost.output_cost == 0.0
    assert cost.total_cost == 2.0
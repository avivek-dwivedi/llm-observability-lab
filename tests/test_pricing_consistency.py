"""Tests for pricing consistency and precedence (single source of truth)."""

from pathlib import Path

import pytest

from observability.pricing import (
    PricingConfig,
    DEFAULT_CATALOG,
    env_pricing_override,
    resolve_pricing,
    estimate_cost,
)
from observability.usage import Usage


@pytest.fixture(autouse=True)
def _clean_pricing_env(monkeypatch):
    """Ensure pricing env vars don't leak between tests."""
    monkeypatch.delenv("PRICE_INPUT_PER_M", raising=False)
    monkeypatch.delenv("PRICE_OUTPUT_PER_M", raising=False)


# ── catalog ───────────────────────────────────────────────────────────────

def test_catalog_pricing_allam():
    u = Usage(1_000_000, 1_000_000, 2_000_000)
    cost = estimate_cost(u, "allam-2-7b")
    assert cost is not None
    cfg = DEFAULT_CATALOG["allam-2-7b"]
    assert cost.input_cost == cfg.input_per_m
    assert cost.output_cost == cfg.output_per_m
    assert cost.source == "configured"


def test_catalog_unknown_model_no_env_returns_none():
    """Unknown model + no env override → missing pricing, never $0."""
    assert resolve_pricing("totally-unknown-model-xyz") is None
    assert estimate_cost(Usage(10, 20, 30), "totally-unknown-model-xyz") is None


# ── precedence ────────────────────────────────────────────────────────────

def test_env_override_wins_over_catalog(monkeypatch):
    monkeypatch.setenv("PRICE_INPUT_PER_M", "5.00")
    monkeypatch.setenv("PRICE_OUTPUT_PER_M", "15.00")
    cfg = resolve_pricing("allam-2-7b")  # catalog has 50/150
    assert cfg == PricingConfig(5.00, 15.00)


def test_partial_env_override_is_ignored(monkeypatch):
    """Only one of the two env vars set → no override, fall to catalog."""
    monkeypatch.setenv("PRICE_INPUT_PER_M", "5.00")
    assert env_pricing_override() is None
    assert resolve_pricing("allam-2-7b") == DEFAULT_CATALOG["allam-2-7b"]


def test_invalid_env_override_raises(monkeypatch):
    monkeypatch.setenv("PRICE_INPUT_PER_M", "abc")
    monkeypatch.setenv("PRICE_OUTPUT_PER_M", "15.00")
    with pytest.raises(ValueError):
        env_pricing_override()


def test_explicit_config_wins_over_everything(monkeypatch):
    monkeypatch.setenv("PRICE_INPUT_PER_M", "5.00")
    monkeypatch.setenv("PRICE_OUTPUT_PER_M", "15.00")
    cost = estimate_cost(
        Usage(1_000_000, 0, 1_000_000),
        "allam-2-7b",
        config=PricingConfig(input_per_m=2.0, output_per_m=4.0),
    )
    assert cost is not None
    assert cost.total_cost == 2.0  # explicit config beats env + catalog


# ── cross-platform consistency ───────────────────────────────────────────

def test_langfuse_setup_uses_same_resolution():
    """setup_langfuse_model.py must derive its prices from observability.pricing.

    Static check: the script imports resolve_pricing and must not carry its
    own hard-coded per-M price literals.
    """
    src = (Path(__file__).resolve().parent.parent
           / "infrastructure" / "setup_langfuse_model.py").read_text(encoding="utf-8")
    assert "resolve_pricing" in src
    assert "INPUT_PRICE =" not in src and "OUTPUT_PRICE =" not in src
    assert "0.000005" not in src and "0.000015" not in src
    assert "5.00" not in src.replace("5.00\"", "") or "PRICE_INPUT_PER_M" in src


def test_env_override_and_app_estimate_agree(monkeypatch):
    """With env override set, app estimate and Langfuse would use same prices."""
    monkeypatch.setenv("PRICE_INPUT_PER_M", "5.00")
    monkeypatch.setenv("PRICE_OUTPUT_PER_M", "15.00")
    u = Usage(1_000_000, 1_000_000, 2_000_000)
    cfg = resolve_pricing("allam-2-7b")
    cost = estimate_cost(u, "allam-2-7b")
    assert cfg is not None and cost is not None
    assert cost.total_cost == cfg.input_per_m + cfg.output_per_m  # 20.0
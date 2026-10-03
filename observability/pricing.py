"""Estimated cost telemetry.

IMPORTANT — the three tiers we keep separate:

1. **provider-reported cost** — Groq does not currently report monetary cost
   in its usage payload, so this is typically ``None``.
2. **configured estimated cost** — computed here from input/output token counts
   and a configurable per-million-token price.  This is an *estimate*, never an
   actual bill.
3. **missing pricing** — when the model is not in the price table we return
   ``None`` and callers MUST label the result "missing pricing" rather than $0.

Use ONE consistent price configuration when comparing dashboards so differences
are attributable to observed usage, not to differing price catalogs.

Precedence (highest wins):
  1. explicit ``PricingConfig`` passed by the caller
  2. ``PRICE_INPUT_PER_M`` / ``PRICE_OUTPUT_PER_M`` environment override
  3. known-model entry in ``DEFAULT_CATALOG``
  4. unknown model with no config → ``None`` ("missing pricing"), never $0

``setup_langfuse_model.py`` resolves prices through the same module so
Prometheus/Grafana and Langfuse can never disagree for the same model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from observability.usage import Usage

# Legacy hard-coded fallback used before the catalog existed.  Kept ONLY as
# the env-var default so existing .env files keep resolving to the same
# numbers they always did.  Not used for models present in the catalog.
_ENV_FALLBACK_INPUT_PER_M = 50.00
_ENV_FALLBACK_OUTPUT_PER_M = 150.00


@dataclass(frozen=True)
class PricingConfig:
    """USD per 1M tokens."""

    input_per_m: float
    output_per_m: float

    @classmethod
    def from_env(cls) -> "PricingConfig":
        """Env override values. Explicitly set env vars win over the catalog;
        unset env vars fall back to the catalog-era defaults."""
        return cls(
            input_per_m=float(os.getenv("PRICE_INPUT_PER_M", _ENV_FALLBACK_INPUT_PER_M)),
            output_per_m=float(os.getenv("PRICE_OUTPUT_PER_M", _ENV_FALLBACK_OUTPUT_PER_M)),
        )


def env_pricing_override() -> PricingConfig | None:
    """Return a PricingConfig only when BOTH price env vars are explicitly set.

    This distinguishes "the operator pinned prices in the environment"
    (precedence 2) from "no override configured" (fall through to the model
    catalog).  Unset or empty variables → None.
    """
    raw_in = os.getenv("PRICE_INPUT_PER_M", "").strip()
    raw_out = os.getenv("PRICE_OUTPUT_PER_M", "").strip()
    if not raw_in or not raw_out:
        return None
    try:
        return PricingConfig(input_per_m=float(raw_in), output_per_m=float(raw_out))
    except ValueError:
        log_bad = raw_in  # keep the offending value visible in the message
        raise ValueError(
            f"Invalid PRICE_INPUT_PER_M/PRICE_OUTPUT_PER_M env values: "
            f"'{log_bad}', '{raw_out}' are not numbers"
        )


def resolve_pricing(model: str | None) -> PricingConfig | None:
    """Resolve the effective pricing for a model (precedence 2 → 3 → 4).

    Returns ``None`` when the model is unknown and no env override exists —
    callers must surface "missing pricing", never $0.
    """
    override = env_pricing_override()
    if override is not None:
        return override
    if model and model in DEFAULT_CATALOG:
        return DEFAULT_CATALOG[model]
    return None


# A small, explicit catalog.  Add rows as needed.
# Prices are USD per 1 million tokens.  These are *illustrative* — they use
# premium-model-level pricing so dashboard cost numbers are large enough to
# be visually meaningful in demos (not a real bill).
# NOTE: the operator env override (PRICE_INPUT_PER_M / PRICE_OUTPUT_PER_M)
# always wins over these entries — see resolve_pricing().
DEFAULT_CATALOG: dict[str, PricingConfig] = {
    "allam-2-7b": PricingConfig(input_per_m=50.00, output_per_m=150.00),
    "llama-3.1-8b-instant": PricingConfig(input_per_m=0.05, output_per_m=0.08),
    "llama-3.3-70b-versatile": PricingConfig(
        input_per_m=0.59, output_per_m=0.79
    ),
}


@dataclass(frozen=True)
class CostEstimate:
    input_cost: float
    output_cost: float
    total_cost: float
    source: str  # "configured" | "provider" | "missing"


def estimate_cost(
    usage: Usage,
    model: str | None = None,
    *,
    config: PricingConfig | None = None,
) -> CostEstimate | None:
    """Return an estimated cost, or ``None`` when pricing is missing.

    Precedence:
      1. explicit ``config`` argument
      2. env override (PRICE_INPUT_PER_M + PRICE_OUTPUT_PER_M both set)
      3. known-model catalog entry
      4. otherwise ``None`` — surface "missing pricing", not $0.
    """
    cfg = config
    if cfg is None:
        cfg = resolve_pricing(model)
    if cfg is None:
        return None

    input_cost = usage.input_tokens * cfg.input_per_m / 1_000_000
    output_cost = usage.output_tokens * cfg.output_per_m / 1_000_000
    return CostEstimate(
        input_cost=round(input_cost, 6),
        output_cost=round(output_cost, 6),
        total_cost=round(input_cost + output_cost, 6),
        source="configured",
    )
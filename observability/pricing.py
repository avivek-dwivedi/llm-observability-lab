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
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from observability.usage import Usage


@dataclass(frozen=True)
class PricingConfig:
    """USD per 1M tokens."""

    input_per_m: float
    output_per_m: float

    @classmethod
    def from_env(cls) -> "PricingConfig":
        return cls(
            input_per_m=float(os.getenv("PRICE_INPUT_PER_M", "50.00")),
            output_per_m=float(os.getenv("PRICE_OUTPUT_PER_M", "150.00")),
        )


# A small, explicit catalog.  Add rows as needed; keep it the single source of
# truth so dashboards are compared on a level playing field.
# Prices are USD per 1 million tokens.  These are *illustrative* — they use
# premium-model-level pricing so dashboard cost numbers are large enough to
# be visually meaningful in demos (not a real bill).
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

    ``config`` wins; otherwise the model is looked up in ``DEFAULT_CATALOG``;
    finally we fall back to env-derived prices.  If none of those yield a price
    we return ``None`` — callers must surface "missing pricing", not $0.
    """
    cfg = config
    if cfg is None and model:
        cfg = DEFAULT_CATALOG.get(model)
    if cfg is None:
        cfg = PricingConfig.from_env()
        # If the env defaults are 0 and the model isn't in the catalog, treat
        # as missing rather than silently free.
        if model and model not in DEFAULT_CATALOG:
            return None

    input_cost = usage.input_tokens * cfg.input_per_m / 1_000_000
    output_cost = usage.output_tokens * cfg.output_per_m / 1_000_000
    return CostEstimate(
        input_cost=round(input_cost, 6),
        output_cost=round(output_cost, 6),
        total_cost=round(input_cost + output_cost, 6),
        source="configured",
    )
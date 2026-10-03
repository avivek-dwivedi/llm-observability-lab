"""SLO calculations for the LLM observability lab.

Two illustrative **internal** SLOs:

1. **7-day request success ≥ 99.5%**
     - Error budget: 0.5% of requests may fail over 7 days.
     - error_budget_total = total_requests * 0.005
     - error_budget_consumed = actual_errors / error_budget_total
     - error_budget_remaining = 1 - error_budget_consumed

2. **≥ 95% of successful logical requests complete within 4 seconds**
     - Uses the histogram bucket at le=4.
     - pct_under_4s = count(le=4) / count(total)

A **hypothetical 99% monthly SLA** is documented separately — it is NOT an
internal SLO and must not be represented as a provider's contractual SLA.

Insufficient-data state:
  - When sample_count < MIN_SAMPLES (default 100), SLO evaluations return
    `None` and callers must surface "insufficient data" rather than a
    misleading percentage.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_SAMPLES = 100  # below this, we don't have enough data for SLO evaluation

# SLO targets
SLO_SUCCESS_RATE_7D = 0.995
SLO_LATENCY_PCT_UNDER_4S = 0.95
SLO_LATENCY_THRESHOLD_S = 4.0

# Hypothetical monthly SLA (documented separately, not computed as internal SLO)
HYPOTHETICAL_MONTHLY_SLA = 0.99


@dataclass(frozen=True)
class SLOResult:
    """Result of an SLO evaluation."""

    name: str
    target: float
    actual: float | None  # None = insufficient data
    sample_count: int
    is_met: bool | None  # None = insufficient data
    error_budget_consumed: float | None  # 0.0 = none, 1.0 = exhausted
    error_budget_remaining: float | None
    insufficient_data: bool
    detail: str


def evaluate_success_slo(
    total_requests: int,
    successful_requests: int,
) -> SLOResult:
    """Evaluate the 7-day success-rate SLO (≥ 99.5%).

    Returns an SLOResult.  If total_requests < MIN_SAMPLES, the result is
    marked insufficient_data and actual/is_met/budget are None.
    """
    insufficient = total_requests < MIN_SAMPLES

    if insufficient or total_requests == 0:
        return SLOResult(
            name="7-day request success ≥ 99.5%",
            target=SLO_SUCCESS_RATE_7D,
            actual=None,
            sample_count=total_requests,
            is_met=None,
            error_budget_consumed=None,
            error_budget_remaining=None,
            insufficient_data=True,
            detail=f"Only {total_requests} samples (minimum {MIN_SAMPLES})",
        )

    actual = successful_requests / total_requests
    allowed_errors = total_requests * (1.0 - SLO_SUCCESS_RATE_7D)
    actual_errors = total_requests - successful_requests

    if allowed_errors > 0:
        budget_consumed = actual_errors / allowed_errors
    else:
        budget_consumed = 0.0 if actual_errors == 0 else 1.0

    budget_remaining = max(0.0, 1.0 - budget_consumed)

    return SLOResult(
        name="7-day request success ≥ 99.5%",
        target=SLO_SUCCESS_RATE_7D,
        actual=actual,
        sample_count=total_requests,
        is_met=actual >= SLO_SUCCESS_RATE_7D,
        error_budget_consumed=budget_consumed,
        error_budget_remaining=budget_remaining,
        insufficient_data=False,
        detail=(
            f"{successful_requests}/{total_requests} successful, "
            f"budget consumed: {budget_consumed:.1%}, "
            f"remaining: {budget_remaining:.1%}"
        ),
    )


def evaluate_latency_slo(
    total_requests: int,
    requests_under_4s: int,
) -> SLOResult:
    """Evaluate the latency SLO (≥ 95% under 4 seconds).

    Only counts *successful* requests (failures are excluded from the
    latency SLO per the "eligible successful logical requests" wording).
    """
    insufficient = total_requests < MIN_SAMPLES

    if insufficient or total_requests == 0:
        return SLOResult(
            name="≥ 95% under 4 seconds",
            target=SLO_LATENCY_PCT_UNDER_4S,
            actual=None,
            sample_count=total_requests,
            is_met=None,
            error_budget_consumed=None,
            error_budget_remaining=None,
            insufficient_data=True,
            detail=f"Only {total_requests} samples (minimum {MIN_SAMPLES})",
        )

    actual = requests_under_4s / total_requests
    is_met = actual >= SLO_LATENCY_PCT_UNDER_4S

    return SLOResult(
        name="≥ 95% under 4 seconds",
        target=SLO_LATENCY_PCT_UNDER_4S,
        actual=actual,
        sample_count=total_requests,
        is_met=is_met,
        error_budget_consumed=None,  # latency SLO doesn't use error budget
        error_budget_remaining=None,
        insufficient_data=False,
        detail=(
            f"{requests_under_4s}/{total_requests} under 4s "
            f"({actual:.1%})"
        ),
    )


def format_slo_report(
    success_slo: SLOResult,
    latency_slo: SLOResult,
) -> str:
    """Format a human-readable SLO report."""
    lines = [
        "=" * 60,
        "  SLO REPORT",
        "=" * 60,
        "",
    ]

    for slo in (success_slo, latency_slo):
        lines.append(f"  SLO: {slo.name}")
        lines.append(f"  Target: {slo.target:.1%}")
        lines.append(f"  Samples: {slo.sample_count}")

        if slo.insufficient_data:
            lines.append(f"  Status: INSUFFICIENT DATA")
            lines.append(f"  Detail: {slo.detail}")
        else:
            status = "✅ MET" if slo.is_met else "❌ VIOLATED"
            lines.append(f"  Actual: {slo.actual:.1%}")
            lines.append(f"  Status: {status}")
            lines.append(f"  Detail: {slo.detail}")
            if slo.error_budget_consumed is not None:
                lines.append(
                    f"  Error budget consumed: {slo.error_budget_consumed:.1%}"
                )
                lines.append(
                    f"  Error budget remaining: {slo.error_budget_remaining:.1%}"
                )
        lines.append("")

    lines.append("  Hypothetical 99% monthly SLA (documented separately):")
    lines.append(f"    This is NOT an internal SLO and must not be")
    lines.append(f"    represented as a provider's contractual SLA.")
    lines.append(f"    Target: {HYPOTHETICAL_MONTHLY_SLA:.0%} / month")
    lines.append("")
    return "\n".join(lines)
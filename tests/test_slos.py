"""Tests for the SLO module — error budget, insufficient data, edge cases."""

from observability.slos import (
    evaluate_success_slo,
    evaluate_latency_slo,
    format_slo_report,
    MIN_SAMPLES,
    SLO_SUCCESS_RATE_7D,
    SLO_LATENCY_PCT_UNDER_4S,
    HYPOTHETICAL_MONTHLY_SLA,
)


def test_success_slo_met():
    # 1000 requests, 997 success → 99.7% ≥ 99.5%
    r = evaluate_success_slo(1000, 997)
    assert not r.insufficient_data
    assert r.is_met is True
    assert r.actual == 997 / 1000
    # 3 errors, allowed = 1000 * 0.005 = 5, consumed = 3/5 = 0.6
    assert r.error_budget_consumed is not None
    assert abs(r.error_budget_consumed - 0.6) < 0.01
    assert r.error_budget_remaining is not None
    assert abs(r.error_budget_remaining - 0.4) < 0.01


def test_success_slo_violated():
    # 1000 requests, 990 success → 99.0% < 99.5%
    r = evaluate_success_slo(1000, 990)
    assert not r.insufficient_data
    assert r.is_met is False
    assert r.actual == 0.99
    # 10 errors, allowed = 5, consumed = 10/5 = 2.0 (exhausted)
    assert r.error_budget_consumed is not None
    assert r.error_budget_consumed > 1.0


def test_success_slo_insufficient_data():
    r = evaluate_success_slo(50, 49)
    assert r.insufficient_data is True
    assert r.actual is None
    assert r.is_met is None
    assert r.error_budget_consumed is None
    assert "insufficient" in r.detail.lower() or "minimum" in r.detail.lower()


def test_success_slo_zero_requests():
    r = evaluate_success_slo(0, 0)
    assert r.insufficient_data is True


def test_latency_slo_met():
    # 200 successful requests, 195 under 4s → 97.5% ≥ 95%
    r = evaluate_latency_slo(200, 195)
    assert not r.insufficient_data
    assert r.is_met is True
    assert r.actual == 195 / 200


def test_latency_slo_violated():
    # 200 requests, 180 under 4s → 90% < 95%
    r = evaluate_latency_slo(200, 180)
    assert not r.insufficient_data
    assert r.is_met is False
    assert r.actual == 0.90


def test_latency_slo_insufficient_data():
    r = evaluate_latency_slo(50, 48)
    assert r.insufficient_data is True
    assert r.actual is None


def test_slo_report_format():
    s = evaluate_success_slo(1000, 997)
    l = evaluate_latency_slo(997, 950)
    report = format_slo_report(s, l)
    assert "SLO REPORT" in report
    assert "99.5%" in report
    assert "95%" in report or "95.0%" in report
    assert "hypothetical" in report.lower() or "SLA" in report


def test_slo_report_insufficient():
    s = evaluate_success_slo(10, 9)
    l = evaluate_latency_slo(9, 8)
    report = format_slo_report(s, l)
    assert "INSUFFICIENT" in report


def test_constants():
    assert SLO_SUCCESS_RATE_7D == 0.995
    assert SLO_LATENCY_PCT_UNDER_4S == 0.95
    assert HYPOTHETICAL_MONTHLY_SLA == 0.99
    assert MIN_SAMPLES == 100
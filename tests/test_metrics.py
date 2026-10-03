"""Tests for the metrics module — instrument creation, recording, flush.

These tests use an in-memory metric reader so no network/exporter is needed.
"""

from unittest.mock import patch

from observability import metrics as mod


def _dummy_exporter():
    from opentelemetry.sdk.metrics.export import MetricExportResult

    class _Dummy:
        _preferred_temporality = None
        _preferred_aggregation = None

        def export(self, _data, timeout_millis=None):
            return MetricExportResult.SUCCESS

        def shutdown(self, timeout=None):
            pass

        def force_flush(self, timeout_millis=None):
            return True

    return _Dummy()


def test_configure_metrics_idempotent():
    with patch.object(mod, "_build_metric_exporter", return_value=_dummy_exporter()):
        mod._METER_PROVIDER = None
        p1 = mod.configure_metrics()
        p2 = mod.configure_metrics()
        assert p1 is p2
        mod.shutdown_metrics()


def test_record_request_no_crash():
    with patch.object(mod, "_build_metric_exporter", return_value=_dummy_exporter()):
        mod._METER_PROVIDER = None
        mod.configure_metrics()
        # Should not raise
        mod.record_request(model="test-model", workflow="test", result="success")
        mod.flush_metrics()
        mod.shutdown_metrics()


def test_record_tokens_no_crash():
    with patch.object(mod, "_build_metric_exporter", return_value=_dummy_exporter()):
        mod._METER_PROVIDER = None
        mod.configure_metrics()
        mod.record_tokens(input_tokens=100, output_tokens=200, model="test", workflow="w")
        mod.flush_metrics()
        mod.shutdown_metrics()


def test_record_cost_no_crash():
    with patch.object(mod, "_build_metric_exporter", return_value=_dummy_exporter()):
        mod._METER_PROVIDER = None
        mod.configure_metrics()
        mod.record_cost(cost_usd=0.001, model="test", workflow="w")
        mod.flush_metrics()
        mod.shutdown_metrics()


def test_record_attempt_no_crash():
    with patch.object(mod, "_build_metric_exporter", return_value=_dummy_exporter()):
        mod._METER_PROVIDER = None
        mod.configure_metrics()
        mod.record_attempt(outcome="timeout", model="test", workflow="w", attempt_number=2)
        mod.flush_metrics()
        mod.shutdown_metrics()


def test_record_duration_no_crash():
    with patch.object(mod, "_build_metric_exporter", return_value=_dummy_exporter()):
        mod._METER_PROVIDER = None
        mod.configure_metrics()
        mod.record_duration(duration_s=0.5, model="test", workflow="w", result="success")
        mod.flush_metrics()
        mod.shutdown_metrics()


def test_record_without_configure_warns():
    mod._METER_PROVIDER = None
    # Should not crash, just warn
    mod.record_request(model="test", workflow="w", result="success")


def test_duration_buckets_include_4s():
    """The histogram MUST include a 4-second bucket boundary for the SLO."""
    assert 4.0 in mod._DURATION_BUCKETS
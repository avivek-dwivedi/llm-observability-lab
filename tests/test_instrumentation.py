"""Tests for the OTel instrumentation setup (no real exporter / network).

These verify the single-provider / no-double-instrumentation contract without
sending spans anywhere.  We patch the exporter to a no-op.
"""

from unittest.mock import patch

from observability import instrumentation as inst


def test_configure_otel_is_idempotent():
    with patch.object(inst, "_build_exporter") as fake_exp:
        # Return a dummy exporter object so BatchSpanProcessor is happy.
        class _DummyExporter:
            def export(self, _spans):
                return 0

            def shutdown(self):
                pass

            def force_flush(self, _t=None):
                return True

        fake_exp.return_value = _DummyExporter()

        # Reset module state
        inst._PROVIDER = None
        inst._INSTRUMENTED = False

        p1 = inst.configure_otel(service_name="test")
        p2 = inst.configure_otel(service_name="test")
        assert p1 is p2  # same provider returned twice
        # _INSTRUMENTED may stay False if openinference isn't installed in CI,
        # but configure_otel must not raise.
        inst.shutdown_otel()


def test_workflow_span_creates_span():
    from opentelemetry import trace
    from observability.instrumentation import configure_otel, workflow_span, shutdown_otel

    with patch.object(inst, "_build_exporter") as fake_exp:
        class _DummyExporter:
            def export(self, _s):
                return 0

            def shutdown(self):
                pass

            def force_flush(self, _t=None):
                return True

        fake_exp.return_value = _DummyExporter()
        inst._PROVIDER = None
        inst._INSTRUMENTED = False
        configure_otel(service_name="test-wf")

        with workflow_span("test.workflow") as span:
            ctx = span.get_span_context()
            assert ctx.trace_id != 0
            assert ctx.span_id != 0

        shutdown_otel()
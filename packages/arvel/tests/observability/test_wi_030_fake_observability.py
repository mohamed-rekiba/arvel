"""Story 10: FakeObservability testing utilities — FR-030-031..032."""

from __future__ import annotations

import pytest


class TestFakeObservabilityImport:
    def test_importable_from_arvel_testing(self) -> None:
        from arvel.testing.observability import FakeObservability

        _ = FakeObservability

    def test_is_context_manager(self) -> None:
        from arvel.testing.observability import FakeObservability

        obs = FakeObservability()
        assert hasattr(obs, "__enter__")
        assert hasattr(obs, "__exit__")


class TestFakeObservabilityCapture:
    def test_captures_log_records(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("test.capture")

        assert any(r.body == "test.capture" for r in obs.log_records)

    def test_captures_spans(self) -> None:
        from arvel.testing.observability import FakeObservability
        from opentelemetry import trace

        with FakeObservability() as obs:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("test.span"):
                pass

        assert any(s.name == "test.span" for s in obs.spans)

    def test_log_records_empty_initially(self) -> None:
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            pass

        assert obs.log_records == []

    def test_spans_empty_initially(self) -> None:
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            pass

        assert obs.spans == []

    def test_context_restores_after_exit(self) -> None:
        from arvel.testing.observability import FakeObservability
        from opentelemetry import trace

        original_tracer_provider = trace.get_tracer_provider()

        with FakeObservability():
            pass

        # Provider restored to what it was before
        assert trace.get_tracer_provider() is original_tracer_provider


class TestAssertLogged:
    def test_assert_logged_passes_when_event_present(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("order.placed", order_id=1)
        obs.assert_logged("order.placed", order_id=1)

    def test_assert_logged_fails_when_event_absent(self) -> None:
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            pass

        with pytest.raises(AssertionError):
            obs.assert_logged("missing.event")

    def test_assert_logged_fails_when_attrs_mismatch(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("order.placed", order_id=1)

        with pytest.raises(AssertionError):
            obs.assert_logged("order.placed", order_id=99)


class TestAssertSpan:
    def test_assert_span_passes_when_present(self) -> None:
        from arvel.testing.observability import FakeObservability
        from opentelemetry import trace

        with FakeObservability() as obs:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("arvel.http.request"):
                pass
        obs.assert_span("arvel.http.request")

    def test_assert_span_fails_when_absent(self) -> None:
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            pass

        with pytest.raises(AssertionError):
            obs.assert_span("missing.span")


class TestAssertNoErrorLogs:
    def test_assert_no_error_logs_passes_with_only_info(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("info.event")
        obs.assert_no_error_logs()

    def test_assert_no_error_logs_fails_with_error_log(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.error("something.broke")

        with pytest.raises(AssertionError):
            obs.assert_no_error_logs()


class TestRecordingLogManagerDeleted:
    def test_recording_log_manager_no_longer_exists(self) -> None:
        import importlib

        try:
            mod = importlib.import_module("arvel.logging.testing")
            assert not hasattr(mod, "RecordingLogManager"), (
                "RecordingLogManager must be removed from arvel.logging.testing"
            )
        except ImportError:
            pass  # Module removed entirely is fine


class TestFakeObservabilityAsyncSafe:
    @pytest.mark.asyncio
    async def test_fake_observability_works_in_async_tests(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("async.event")
        obs.assert_logged("async.event")

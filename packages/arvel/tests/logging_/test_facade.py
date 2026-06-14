"""Tests for the Log facade — bound (LogManager) and unbound (OtelLogger fallback) paths."""

from __future__ import annotations


class TestLogFacadeBound:
    def test_bound_channel_returns_named_channel(self) -> None:
        from arvel.logging.channels.null_channel import NullChannel
        from arvel.logging.facade import Log
        from arvel.logging.manager import LogManager

        Log.bind(LogManager(default="null", channels={"null": {"driver": "null"}}))
        try:
            assert isinstance(Log.channel("null"), NullChannel)
        finally:
            Log.unbind()

    def test_bound_stack_returns_stack_channel(self) -> None:
        from arvel.logging.channels.stack_channel import StackChannel
        from arvel.logging.facade import Log
        from arvel.logging.manager import LogManager

        Log.bind(
            LogManager(
                default="otel",
                channels={"otel": {"driver": "otel"}, "null": {"driver": "null"}},
            )
        )
        try:
            assert isinstance(Log.stack("otel", "null"), StackChannel)
        finally:
            Log.unbind()

    def test_bound_share_context_reaches_channel(self) -> None:
        from arvel.logging.facade import Log
        from arvel.logging.manager import LogManager
        from arvel.testing.observability import FakeObservability

        Log.bind(LogManager(default="otel", channels={"otel": {"driver": "otel"}}))
        try:
            with FakeObservability() as obs:
                Log.share_context(env="prod")
                Log.info("ctx.shared")
            obs.assert_logged("ctx.shared", env="prod")
        finally:
            Log.unbind()

    def test_bound_flush_shared_context_clears_fields(self) -> None:
        from arvel.logging.facade import Log
        from arvel.logging.manager import LogManager
        from arvel.testing.observability import FakeObservability

        Log.bind(LogManager(default="otel", channels={"otel": {"driver": "otel"}}))
        try:
            Log.share_context(env="prod")
            Log.flush_shared_context()
            with FakeObservability() as obs:
                Log.info("ctx.flushed")
            records = obs.log_records
            assert all("env" not in str(r.attributes) for r in records)
        finally:
            Log.unbind()

    def test_bound_with_context_binds_fields(self) -> None:
        from arvel.logging.facade import Log
        from arvel.logging.manager import LogManager
        from arvel.testing.observability import FakeObservability

        Log.bind(LogManager(default="otel", channels={"otel": {"driver": "otel"}}))
        try:
            child = Log.with_context(user_id=5)
            with FakeObservability() as obs:
                child.info("child.log")
            obs.assert_logged("child.log", user_id=5)
        finally:
            Log.unbind()

    def test_bound_levels_delegate_to_manager(self) -> None:
        from arvel.logging.facade import Log
        from arvel.logging.manager import LogManager
        from arvel.testing.observability import FakeObservability

        Log.bind(LogManager(default="otel", channels={"otel": {"driver": "otel"}}))
        try:
            with FakeObservability() as obs:
                Log.info("i")
                Log.warning("w")
                Log.error("e")
                Log.critical("c")
            obs.assert_logged("i")
            obs.assert_logged("w")
        finally:
            Log.unbind()


class TestLogFacadeUnbound:
    def test_unbound_channel_returns_otel_channel(self) -> None:
        from arvel.logging.channels.otel_channel import OtelChannel
        from arvel.logging.facade import Log
        from arvel.testing.observability import FakeObservability

        Log.unbind()
        with FakeObservability():
            channel = Log.channel("audit")
        assert isinstance(channel, OtelChannel)

    def test_unbound_stack_returns_otel_channel(self) -> None:
        from arvel.logging.channels.otel_channel import OtelChannel
        from arvel.logging.facade import Log
        from arvel.testing.observability import FakeObservability

        Log.unbind()
        with FakeObservability():
            channel = Log.stack("a", "b")
        assert isinstance(channel, OtelChannel)

    def test_unbound_share_and_flush_are_noops(self) -> None:
        from arvel.logging.facade import Log

        Log.unbind()
        # No manager bound — these must be safe no-ops, not raise.
        Log.share_context(x=1)
        Log.flush_shared_context()

    def test_unbound_with_context_falls_back_to_otel_logger(self) -> None:
        from arvel.logging.facade import Log
        from arvel.testing.observability import FakeObservability

        Log.unbind()
        with FakeObservability() as obs:
            child = Log.with_context(trace="t-1")
            child.info("fallback.child")
        obs.assert_logged("fallback.child", trace="t-1")

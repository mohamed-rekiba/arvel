"""Tests for LogManager — channel factory, shareContext, withContext, emergency fallback."""

from __future__ import annotations


class TestLogManagerChannelResolution:
    def test_channel_returns_otel_channel_for_otel_driver(self) -> None:
        from arvel.logging.channels.otel_channel import OtelChannel
        from arvel.logging.manager import LogManager

        mgr = LogManager(default="otel", channels={"otel": {"driver": "otel"}})
        assert isinstance(mgr.channel(), OtelChannel)

    def test_channel_is_cached_after_first_build(self) -> None:
        from arvel.logging.manager import LogManager

        mgr = LogManager(default="otel", channels={"otel": {"driver": "otel"}})
        c1 = mgr.channel()
        c2 = mgr.channel()
        assert c1 is c2

    def test_channel_builds_null_driver(self) -> None:
        from arvel.logging.channels.null_channel import NullChannel
        from arvel.logging.manager import LogManager

        mgr = LogManager(default="null", channels={"null": {"driver": "null"}})
        assert isinstance(mgr.channel(), NullChannel)

    def test_channel_builds_stderr_driver(self) -> None:
        from arvel.logging.channels.stderr_channel import StderrChannel
        from arvel.logging.manager import LogManager

        mgr = LogManager(
            default="stderr", channels={"stderr": {"driver": "stderr", "level": "info"}}
        )
        assert isinstance(mgr.channel(), StderrChannel)

    def test_channel_builds_stack_driver(self) -> None:
        from arvel.logging.channels.stack_channel import StackChannel
        from arvel.logging.manager import LogManager

        mgr = LogManager(
            default="stack",
            channels={
                "stack": {"driver": "stack", "channels": ["otel"]},
                "otel": {"driver": "otel"},
            },
        )
        assert isinstance(mgr.channel(), StackChannel)

    def test_stack_method_returns_stack_channel(self) -> None:
        from arvel.logging.channels.stack_channel import StackChannel
        from arvel.logging.manager import LogManager

        mgr = LogManager(
            default="otel",
            channels={
                "otel": {"driver": "otel"},
                "null": {"driver": "null"},
            },
        )
        ch = mgr.stack("otel", "null")
        assert isinstance(ch, StackChannel)

    def test_unknown_channel_falls_back_to_emergency_otel(self) -> None:
        from arvel.logging.channels.otel_channel import OtelChannel
        from arvel.logging.manager import LogManager
        from arvel.testing.observability import FakeObservability

        mgr = LogManager(default="no_such_channel", channels={})
        with FakeObservability():
            ch = mgr.channel("no_such_channel")
        assert isinstance(ch, OtelChannel)


class TestLogManagerContextMethods:
    def test_share_context_merges_into_shared_dict(self) -> None:
        from arvel.logging.manager import LogManager

        mgr = LogManager(default="null", channels={"null": {"driver": "null"}})
        mgr.share_context(request_id="xyz")
        assert mgr._shared["request_id"] == "xyz"  # pyright: ignore[reportPrivateUsage]

    def test_flush_shared_context_clears_shared_dict(self) -> None:
        from arvel.logging.manager import LogManager

        mgr = LogManager(default="null", channels={"null": {"driver": "null"}})
        mgr.share_context(a=1, b=2)
        mgr.flush_shared_context()
        assert mgr._shared == {}  # pyright: ignore[reportPrivateUsage]

    def test_with_context_returns_clone_with_bound_fields(self) -> None:
        from arvel.logging.manager import LogManager

        mgr = LogManager(default="null", channels={"null": {"driver": "null"}})
        child = mgr.with_context(user_id=99)
        assert child is not mgr
        assert child._bound == {"user_id": 99}  # pyright: ignore[reportPrivateUsage]

    def test_with_context_shares_shared_dict_with_parent(self) -> None:
        from arvel.logging.manager import LogManager

        mgr = LogManager(default="null", channels={"null": {"driver": "null"}})
        child = mgr.with_context(x=1)
        mgr.share_context(tenant="acme")
        # child sees the shared context change because it references the same dict
        assert child._shared is mgr._shared  # pyright: ignore[reportPrivateUsage]

    def test_with_context_shares_channel_cache(self) -> None:
        from arvel.logging.manager import LogManager

        mgr = LogManager(default="null", channels={"null": {"driver": "null"}})
        _ = mgr.channel()  # prime cache
        child = mgr.with_context(x=1)
        assert child._cache is mgr._cache  # pyright: ignore[reportPrivateUsage]


class TestLogManagerDelegation:
    def test_info_passes_shared_and_bound_context_to_channel(self) -> None:
        from arvel.logging.manager import LogManager
        from arvel.testing.observability import FakeObservability

        mgr = LogManager(default="otel", channels={"otel": {"driver": "otel"}})
        mgr.share_context(env="prod")
        child = mgr.with_context(user_id=7)

        with FakeObservability() as obs:
            child.info("delegate.test")
        obs.assert_logged("delegate.test", env="prod", user_id=7)

    def test_error_with_exc_info_true_attaches_active_exception(self) -> None:
        from arvel.logging.manager import LogManager
        from arvel.testing.observability import FakeObservability

        mgr = LogManager(default="otel", channels={"otel": {"driver": "otel"}})
        with FakeObservability() as obs:
            try:
                raise ValueError("test-err")
            except ValueError:
                mgr.error("caught", exc_info=True)
        records = obs.log_records
        assert any("test-err" in str(r.attributes) for r in records)

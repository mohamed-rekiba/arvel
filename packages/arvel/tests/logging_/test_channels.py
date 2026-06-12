"""Tests for individual LogChannel driver implementations."""

from __future__ import annotations

import pytest


class TestNullChannel:
    def test_null_swallows_all_levels(self) -> None:
        from arvel.logging.channels.null_channel import NullChannel

        ch = NullChannel()
        ch.debug("x")
        ch.info("x")
        ch.warning("x")
        ch.error("x")
        ch.critical("x")
        ch.exception("x")

    def test_null_with_context_returns_self(self) -> None:
        from arvel.logging.channels.null_channel import NullChannel

        ch = NullChannel()
        assert ch.with_context(user_id=1) is ch


class TestStderrChannel:
    def test_stderr_emits_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.logging.channels.stderr_channel import StderrChannel

        ch = StderrChannel(level="debug")
        ch.info("hello.stderr")

        captured = capsys.readouterr()
        assert "hello.stderr" in captured.err

    def test_stderr_with_context_binds_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.logging.channels.stderr_channel import StderrChannel

        ch = StderrChannel(level="debug").with_context(req="abc")
        ch.info("bound.field")
        captured = capsys.readouterr()
        assert "req" in captured.err
        assert "abc" in captured.err

    def test_stderr_level_gating_suppresses_below_threshold(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.logging.channels.stderr_channel import StderrChannel

        ch = StderrChannel(level="error")
        ch.debug("should.not.appear")
        captured = capsys.readouterr()
        assert "should.not.appear" not in captured.err

    def test_stderr_error_attaches_exception(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.logging.channels.stderr_channel import StderrChannel

        ch = StderrChannel(level="debug")
        try:
            raise ValueError("boom")
        except ValueError as exc:
            ch.error("caught", exc=exc)
        captured = capsys.readouterr()
        assert "boom" in captured.err


class TestStackChannel:
    def test_stack_fans_out_to_all_channels(self) -> None:
        from arvel.logging.channels.null_channel import NullChannel
        from arvel.logging.channels.stack_channel import StackChannel

        calls: list[str] = []

        class Recorder:
            def debug(self, message: str, **context: object) -> None:
                calls.append(f"debug:{message}")

            def info(self, message: str, **context: object) -> None:
                calls.append(f"info:{message}")

            def warning(self, message: str, **context: object) -> None:
                calls.append(f"warning:{message}")

            def error(self, message: str, *, exc: object = None, **context: object) -> None:
                calls.append(f"error:{message}")

            def critical(self, message: str, **context: object) -> None:
                calls.append(f"critical:{message}")

            def exception(self, message: str, **context: object) -> None:
                calls.append(f"exception:{message}")

            def with_context(self, **fields: object) -> Recorder:
                return self

        rec = Recorder()
        stack = StackChannel([rec, NullChannel()])
        stack.info("broadcast")
        assert "info:broadcast" in calls

    def test_stack_ignore_exceptions_swallows_channel_errors(self) -> None:
        from arvel.logging.channels.stack_channel import StackChannel

        class Boom:
            def info(self, message: str, **context: object) -> None:
                raise RuntimeError("channel failure")

            def debug(self, message: str, **context: object) -> None:
                pass

            def warning(self, message: str, **context: object) -> None:
                pass

            def error(self, message: str, *, exc: object = None, **context: object) -> None:
                pass

            def critical(self, message: str, **context: object) -> None:
                pass

            def exception(self, message: str, **context: object) -> None:
                pass

            def with_context(self, **fields: object) -> Boom:
                return self

        stack = StackChannel([Boom()], ignore_exceptions=True)
        stack.info("no raise please")  # must not raise

    def test_stack_propagates_exceptions_by_default(self) -> None:
        from arvel.logging.channels.stack_channel import StackChannel

        class Boom:
            def info(self, message: str, **context: object) -> None:
                raise RuntimeError("kaboom")

            def debug(self, message: str, **context: object) -> None:
                pass

            def warning(self, message: str, **context: object) -> None:
                pass

            def error(self, message: str, *, exc: object = None, **context: object) -> None:
                pass

            def critical(self, message: str, **context: object) -> None:
                pass

            def exception(self, message: str, **context: object) -> None:
                pass

            def with_context(self, **fields: object) -> Boom:
                return self

        stack = StackChannel([Boom()], ignore_exceptions=False)
        with pytest.raises(RuntimeError, match="kaboom"):
            stack.info("should raise")

    def test_stack_with_context_clones_all_channels(self) -> None:
        from arvel.logging.channels.null_channel import NullChannel
        from arvel.logging.channels.stack_channel import StackChannel

        ch = StackChannel([NullChannel()])
        child = ch.with_context(x=1)
        assert child is not ch
        assert len(child._channels) == 1  # pyright: ignore[reportPrivateUsage]


class TestOtelChannel:
    def test_otel_channel_delegates_to_otel_logger(self) -> None:
        from arvel.logging.channels.otel_channel import OtelChannel
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            ch = OtelChannel("arvel")
            ch.info("otel.channel.test", key="val")
        obs.assert_logged("otel.channel.test", key="val")

    def test_otel_channel_with_context_binds_fields(self) -> None:
        from arvel.logging.channels.otel_channel import OtelChannel
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            ch = OtelChannel("arvel").with_context(trace_id="abc")
            ch.info("with.ctx")
        obs.assert_logged("with.ctx", trace_id="abc")

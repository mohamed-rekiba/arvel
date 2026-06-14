"""Tests for individual LogChannel driver implementations."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


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


class TestFileChannel:
    def test_single_writes_message_to_file(self, tmp_path: Path) -> None:
        from arvel.logging.channels.file_channel import SingleFileChannel

        log_path = tmp_path / "logs" / "app.log"
        ch = SingleFileChannel(str(log_path), level="debug")
        ch.info("single.file.write", request_id="r-1")

        # _ensure_parent created the nested dir; the handler flushed on emit.
        assert log_path.exists()
        contents = log_path.read_text(encoding="utf-8")
        assert "single.file.write" in contents
        assert "request_id" in contents

    def test_daily_writes_message_to_file(self, tmp_path: Path) -> None:
        from arvel.logging.channels.file_channel import DailyFileChannel

        log_path = tmp_path / "daily.log"
        ch = DailyFileChannel(str(log_path), days=3, level="debug")
        ch.warning("daily.file.write")

        assert log_path.read_text(encoding="utf-8").find("daily.file.write") != -1

    def test_build_file_channel_defaults_to_single(self, tmp_path: Path) -> None:
        from arvel.logging.channels.file_channel import SingleFileChannel, build_file_channel

        ch = build_file_channel({"path": str(tmp_path / "x.log")})
        assert isinstance(ch, SingleFileChannel)

    def test_build_file_channel_selects_daily(self, tmp_path: Path) -> None:
        from arvel.logging.channels.file_channel import DailyFileChannel, build_file_channel

        ch = build_file_channel(
            {"driver": "daily", "path": str(tmp_path / "y.log"), "days": 5, "level": "warning"}
        )
        assert isinstance(ch, DailyFileChannel)


class _FakeSysLogHandler(logging.Handler):
    """Stand-in that records the address it was constructed with."""

    last_address: object = None

    def __init__(self, address: object = None, facility: int = 0) -> None:
        super().__init__()
        type(self).last_address = address

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - no-op sink
        pass


class TestSyslogChannel:
    def test_falls_back_to_stream_handler_on_oserror(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def raise_oserror(*_args: object, **_kwargs: object) -> object:
            raise OSError("no syslog socket")

        monkeypatch.setattr(logging.handlers, "SysLogHandler", raise_oserror)

        from arvel.logging.channels.syslog_channel import SyslogChannel

        ch = SyslogChannel(level="debug")
        ch.info("syslog.fallback")
        assert "syslog.fallback" in capsys.readouterr().err

    def test_uses_darwin_address(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(logging.handlers, "SysLogHandler", _FakeSysLogHandler)
        monkeypatch.setattr(sys, "platform", "darwin")

        from arvel.logging.channels.syslog_channel import SyslogChannel

        SyslogChannel()
        assert _FakeSysLogHandler.last_address == (
            "/var/run/syslog",
            logging.handlers.SYSLOG_UDP_PORT,
        )

    def test_uses_dev_log_address_on_linux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(logging.handlers, "SysLogHandler", _FakeSysLogHandler)
        monkeypatch.setattr(sys, "platform", "linux")

        from arvel.logging.channels.syslog_channel import SyslogChannel

        SyslogChannel()
        assert _FakeSysLogHandler.last_address == "/dev/log"


class _RecordingChannel:
    """LogChannel double that records every call as ``level:message``."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def debug(self, message: str, **context: object) -> None:
        self.calls.append(f"debug:{message}")

    def info(self, message: str, **context: object) -> None:
        self.calls.append(f"info:{message}")

    def warning(self, message: str, **context: object) -> None:
        self.calls.append(f"warning:{message}")

    def error(self, message: str, *, exc: object = None, **context: object) -> None:
        self.calls.append(f"error:{message}")

    def critical(self, message: str, **context: object) -> None:
        self.calls.append(f"critical:{message}")

    def exception(self, message: str, **context: object) -> None:
        self.calls.append(f"exception:{message}")

    def with_context(self, **fields: object) -> _RecordingChannel:
        return self


class TestStackChannelFanOut:
    """Covers the fan-out for every level plus error-path exception handling."""

    def test_every_level_fans_out(self) -> None:
        from arvel.logging.channels.stack_channel import StackChannel

        rec = _RecordingChannel()
        stack = StackChannel([rec])
        stack.debug("d")
        stack.warning("w")
        stack.error("e")
        stack.critical("c")
        stack.exception("x")
        assert rec.calls == ["debug:d", "warning:w", "error:e", "critical:c", "exception:x"]

    def test_error_swallows_when_ignore_exceptions(self) -> None:
        from arvel.logging.channels.stack_channel import StackChannel

        stack = StackChannel([_ErrorBoom()], ignore_exceptions=True)
        stack.error("no raise")  # must not raise

    def test_error_propagates_by_default(self) -> None:
        from arvel.logging.channels.stack_channel import StackChannel

        stack = StackChannel([_ErrorBoom()], ignore_exceptions=False)
        with pytest.raises(RuntimeError, match="err boom"):
            stack.error("should raise")


class _ErrorBoom:
    """LogChannel double whose ``error`` raises; other levels are no-ops."""

    def debug(self, message: str, **context: object) -> None: ...

    def info(self, message: str, **context: object) -> None: ...

    def warning(self, message: str, **context: object) -> None: ...

    def error(self, message: str, *, exc: object = None, **context: object) -> None:
        raise RuntimeError("err boom")

    def critical(self, message: str, **context: object) -> None: ...

    def exception(self, message: str, **context: object) -> None: ...

    def with_context(self, **fields: object) -> _ErrorBoom:
        return self

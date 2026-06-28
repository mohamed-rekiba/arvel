"""Kernel lifecycle services — logging, exception handler, boot reporter."""

from __future__ import annotations

import io
from typing import Any

from arvel.kernel import (
    Application,
    BootReporter,
    ExceptionHandler,
    LogManager,
    ServiceProvider,
    lifespan,
    set_application,
)
from arvel.kernel.provider import KernelServiceProvider


class FakeLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def error(self, event: str, **kw: Any) -> None:
        self.calls.append(("error", event, kw))

    # other levels unused here
    def info(self, event: str, **kw: Any) -> None: ...


# --- logging ---------------------------------------------------------------
def test_logmanager_channel_and_bind_return_logmanager() -> None:
    log = LogManager()
    assert isinstance(log.channel("audit"), LogManager)
    assert isinstance(log.bind(request_id="r1"), LogManager)
    log.info("hello", k=1)  # must not raise


# --- exception handler -----------------------------------------------------
def test_report_logs_when_should_report() -> None:
    logger = FakeLogger()
    handler = ExceptionHandler(logger)
    handler.report(ValueError("boom"))
    assert logger.calls and logger.calls[0][0] == "error"


def test_dont_report_suppresses() -> None:
    logger = FakeLogger()
    handler = ExceptionHandler(logger).dont_report(ValueError)
    assert handler.should_report(ValueError("x")) is False
    assert handler.should_report(KeyError("y")) is True
    handler.report(ValueError("x"))
    assert logger.calls == []


async def test_render_and_console() -> None:
    handler = ExceptionHandler()
    payload = await handler.render(None, KeyError("missing"))
    assert payload["error"] == "KeyError"
    buf = io.StringIO()
    handler.render_for_console(buf, RuntimeError("nope"))
    assert "RuntimeError: nope" in buf.getvalue()


# --- kernel provider bindings ---------------------------------------------
def test_kernel_provider_binds_log_and_exceptions() -> None:
    app = Application()
    KernelServiceProvider(app).register()
    assert isinstance(app.make("log"), LogManager)
    assert isinstance(app.make("exceptions"), ExceptionHandler)
    set_application(None)


# --- boot reporter ---------------------------------------------------------
async def test_boot_reporter_reports_startup_and_shutdown() -> None:
    buf = io.StringIO()  # a StringIO is not a TTY → output must carry no ANSI escape codes
    app = Application()
    BootReporter(app, level="summary", out=buf).register()
    await app.boot()
    await app.terminate()
    output = buf.getvalue()
    assert "ready in" in output
    assert "providers" in output
    assert "shutting down" in output
    assert "\033[" not in output  # no color when piped/redirected/CI (isatty-gated)
    set_application(None)


async def test_boot_reporter_paints_on_a_tty() -> None:
    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    buf = _Tty()
    app = Application()
    BootReporter(app, level="summary", out=buf).register()
    await app.boot()
    await app.terminate()
    assert "\033[35m" in buf.getvalue()  # color on a real terminal
    set_application(None)


async def test_boot_reporter_counts_booted_not_deferred() -> None:
    class DeferredProvider(ServiceProvider):
        def register(self) -> None:
            self.app.singleton("svc", lambda _c: "D")

        def provides(self) -> list[Any]:
            return ["svc"]

    buf = io.StringIO()
    app = Application()
    app.register_deferred(DeferredProvider(app))  # registered (discovered) but not booted
    BootReporter(app, level="summary", out=buf).register()
    await app.boot()
    output = buf.getvalue()
    assert app.booted_provider_count == 0  # only the deferred one is registered
    assert "0 providers (+1 deferred)" in output
    set_application(None)


async def test_boot_reporter_quiet_is_silent() -> None:
    buf = io.StringIO()
    app = Application()
    BootReporter(app, level="quiet", out=buf).register()
    await app.boot()
    await app.terminate()
    assert buf.getvalue() == ""
    set_application(None)


async def test_lifespan_attaches_reporter() -> None:
    app = Application()
    app.make("config").set("app", {"boot_report": "quiet"})
    async with lifespan(app) as running:
        assert running.booted is True
    set_application(None)

"""Per-type log levels, predicate/marker suppression, report throttling, exception
self-handlers, and the global report-context provider."""

from __future__ import annotations

from typing import Any

from arvel.kernel.exceptions import ExceptionHandler, Limit, Lottery, ShouldntReport


class _SpyLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []

    def _record(self, level: str, event: str, **kw: Any) -> None:
        self.records.append((level, event, kw))

    def debug(self, event: str, **kw: Any) -> None:
        self._record("debug", event, **kw)

    def info(self, event: str, **kw: Any) -> None:
        self._record("info", event, **kw)

    def warning(self, event: str, **kw: Any) -> None:
        self._record("warning", event, **kw)

    def error(self, event: str, **kw: Any) -> None:
        self._record("error", event, **kw)

    def critical(self, event: str, **kw: Any) -> None:
        self._record("critical", event, **kw)

    def bind(self, **kw: Any) -> _SpyLogger:
        return self

    def channel(self, name: str) -> _SpyLogger:
        return self


class Boom(RuntimeError):
    pass


# --- per-type log level -----------------------------------------------------------


def test_level_logs_registered_types_at_that_level() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger).level(Boom, "warning")
    handler.report(Boom("x"))
    handler.report(ValueError("y"))
    assert [r[0] for r in logger.records] == ["warning", "error"]


# --- predicate + marker suppression --------------------------------------------------


def test_dont_report_when_predicate_suppresses() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger).dont_report_when(
        lambda exc: isinstance(exc, Boom) and "quiet" in str(exc)
    )
    handler.report(Boom("quiet please"))
    handler.report(Boom("loud"))
    assert len(logger.records) == 1


def test_shouldnt_report_marker_suppresses() -> None:
    class Muted(RuntimeError, ShouldntReport):
        pass

    logger = _SpyLogger()
    handler = ExceptionHandler(logger)
    handler.report(Muted("x"))
    assert logger.records == []


def test_marked_exception_still_renders() -> None:
    class Muted(RuntimeError, ShouldntReport):
        pass

    handler = ExceptionHandler(_SpyLogger())
    handler.renderable(Muted, lambda exc, request: {"rendered": True})
    assert handler.try_render(None, Muted("x")) == {"rendered": True}


# --- throttling -------------------------------------------------------------------


def test_limit_throttle_drops_over_the_window() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger).throttle(lambda exc: Limit(max_attempts=3, per_seconds=60))
    for _ in range(5):
        handler.report(Boom(f"same-{_}"))
    assert len(logger.records) == 3


def test_limit_throttle_window_resets() -> None:
    now = {"t": 0.0}
    logger = _SpyLogger()
    handler = ExceptionHandler(logger, clock=lambda: now["t"]).throttle(
        lambda exc: Limit(max_attempts=1, per_seconds=10)
    )
    handler.report(Boom("a"))
    handler.report(Boom("b"))  # dropped inside the window
    now["t"] = 11.0
    handler.report(Boom("c"))  # new window
    assert len(logger.records) == 2


def test_lottery_none_and_certain() -> None:
    logger = _SpyLogger()
    never = ExceptionHandler(logger).throttle(lambda exc: Lottery(0, 1))
    never.report(Boom("a"))
    assert logger.records == []
    always = ExceptionHandler(logger).throttle(lambda exc: Lottery(1, 1))
    always.report(Boom("b"))
    assert len(logger.records) == 1


def test_throttle_returning_none_means_unthrottled() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger).throttle(lambda exc: None)
    handler.report(Boom("a"))
    handler.report(Boom("b"))
    assert len(logger.records) == 2


# --- exception self-handlers ----------------------------------------------------------


def test_exception_report_method_is_invoked_and_replaces_default() -> None:
    calls: list[str] = []

    class SelfReporting(RuntimeError):
        def report(self) -> None:
            calls.append("reported")

    logger = _SpyLogger()
    ExceptionHandler(logger).report(SelfReporting("x"))
    assert calls == ["reported"]
    assert logger.records == []  # self-handler replaced the default log


def test_exception_report_returning_false_falls_through_to_default() -> None:
    class StillLogged(RuntimeError):
        def report(self) -> bool:
            return False

    logger = _SpyLogger()
    ExceptionHandler(logger).report(StillLogged("x"))
    assert len(logger.records) == 1


def test_exception_render_method_is_consulted() -> None:
    class SelfRendering(RuntimeError):
        def render(self, request: Any) -> Any:
            return {"self": True}

    handler = ExceptionHandler(_SpyLogger())
    assert handler.try_render(None, SelfRendering("x")) == {"self": True}


def test_exception_render_returning_none_falls_through() -> None:
    class Fallthrough(RuntimeError):
        def render(self, request: Any) -> Any:
            return None

    handler = ExceptionHandler(_SpyLogger())
    assert handler.try_render(None, Fallthrough("x")) is None


# --- global context provider ------------------------------------------------------------


def test_global_context_merges_and_per_exception_wins() -> None:
    class WithContext(RuntimeError):
        def context(self) -> dict[str, Any]:
            return {"tenant": "acme"}

    logger = _SpyLogger()
    handler = ExceptionHandler(logger).context(lambda: {"app_version": "1.2", "tenant": "global"})
    handler.report(WithContext("x"))
    (_, _, kw) = logger.records[0]
    assert kw["app_version"] == "1.2"
    assert kw["tenant"] == "acme"  # per-exception context wins over the global provider

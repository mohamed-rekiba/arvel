"""Flow helpers: async-aware retry/rescue with reporting, once(), fakeable Sleep."""

from __future__ import annotations

import pytest

from arvel.kernel.globals import set_application
from arvel.support import Sleep, once, rescue, retry


@pytest.fixture(autouse=True)
def _no_app() -> None:
    set_application(None)


# --- retry: sync ------------------------------------------------------------
def test_retry_sync_succeeds_after_failures() -> None:
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("boom")
        return "ok"

    assert retry(3, flaky) == "ok"
    assert len(calls) == 3


def test_retry_sync_exhaustion_reraises_last_error() -> None:
    with pytest.raises(ValueError, match="always"):
        retry(2, lambda: (_ for _ in ()).throw(ValueError("always")))


def test_retry_backoff_sequence_drives_sleeps() -> None:
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("boom")
        return "ok"

    with Sleep.fake() as slept:
        assert retry(3, flaky, backoff=[0.1, 0.2]) == "ok"
    assert slept == [0.1, 0.2]


def test_retry_backoff_callable_gets_attempt_number() -> None:
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("boom")
        return "ok"

    with Sleep.fake() as slept:
        retry(3, flaky, backoff=lambda attempt: attempt * 1.0)
    assert slept == [1.0, 2.0]


def test_retry_when_predicate_false_reraises_immediately() -> None:
    calls: list[int] = []

    def flaky() -> None:
        calls.append(1)
        raise KeyError("nope")

    with pytest.raises(KeyError):
        retry(5, flaky, when=lambda exc: isinstance(exc, ValueError))
    assert len(calls) == 1


# --- retry: async -----------------------------------------------------------
async def test_retry_awaits_async_callback_with_async_sleep() -> None:
    calls: list[int] = []

    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("boom")
        return "ok"

    with Sleep.fake() as slept:
        assert await retry(3, flaky, sleep=0.05) == "ok"
    assert slept == [0.05]


# --- rescue -----------------------------------------------------------------
def test_rescue_returns_default_on_error() -> None:
    assert rescue(lambda: 1 // 0, default=42) == 42


def test_rescue_returns_result_when_no_error() -> None:
    assert rescue(lambda: 7) == 7


async def test_rescue_awaits_async_callback() -> None:
    async def bad() -> int:
        raise RuntimeError("x")

    assert await rescue(bad, default=9) == 9


def test_rescue_reports_to_bound_exception_handler() -> None:
    from arvel.contracts import ExceptionHandler
    from arvel.kernel.application import Application

    reported: list[BaseException] = []

    class Handler:
        def report(self, exc: BaseException) -> None:
            reported.append(exc)

        def should_report(self, exc: BaseException) -> bool:
            return True

        def try_render(self, request: object, exc: BaseException) -> object | None:
            return None

        async def render(self, request: object, exc: BaseException) -> object:
            return None

        def render_for_console(self, output: object, exc: BaseException) -> None:
            pass

    app = Application()
    app.instance(ExceptionHandler, Handler())
    set_application(app)
    rescue(lambda: 1 // 0, default=0)
    assert len(reported) == 1 and isinstance(reported[0], ZeroDivisionError)
    set_application(None)


def test_rescue_report_false_stays_silent() -> None:
    from arvel.contracts import ExceptionHandler
    from arvel.kernel.application import Application

    reported: list[BaseException] = []

    class Handler:
        def report(self, exc: BaseException) -> None:
            reported.append(exc)

        def should_report(self, exc: BaseException) -> bool:
            return True

        def try_render(self, request: object, exc: BaseException) -> object | None:
            return None

        async def render(self, request: object, exc: BaseException) -> object:
            return None

        def render_for_console(self, output: object, exc: BaseException) -> None:
            pass

    app = Application()
    app.instance(ExceptionHandler, Handler())
    set_application(app)
    rescue(lambda: 1 // 0, default=0, report=False)
    assert reported == []
    set_application(None)


# --- crash/contract edges (review findings) ----------------------------------
def test_retry_empty_backoff_falls_back_to_sleep() -> None:
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("boom")
        return "ok"

    with Sleep.fake() as slept:
        assert retry(2, flaky, sleep=0.3, backoff=[]) == "ok"
    assert slept == [0.3]


def test_rescue_survives_a_raising_exception_handler() -> None:
    from arvel.contracts import ExceptionHandler
    from arvel.kernel.application import Application

    class ExplodingHandler:
        def report(self, exc: BaseException) -> None:
            raise RuntimeError("handler is broken")

        def should_report(self, exc: BaseException) -> bool:
            return True

        def try_render(self, request: object, exc: BaseException) -> object | None:
            return None

        async def render(self, request: object, exc: BaseException) -> object:
            return None

        def render_for_console(self, output: object, exc: BaseException) -> None:
            pass

    app = Application()
    app.instance(ExceptionHandler, ExplodingHandler())
    set_application(app)
    assert rescue(lambda: 1 // 0, default="still-safe") == "still-safe"
    set_application(None)


async def test_async_rescue_reports_and_respects_report_flag() -> None:
    from arvel.contracts import ExceptionHandler
    from arvel.kernel.application import Application

    reported: list[BaseException] = []

    class Handler:
        def report(self, exc: BaseException) -> None:
            reported.append(exc)

        def should_report(self, exc: BaseException) -> bool:
            return True

        def try_render(self, request: object, exc: BaseException) -> object | None:
            return None

        async def render(self, request: object, exc: BaseException) -> object:
            return None

        def render_for_console(self, output: object, exc: BaseException) -> None:
            pass

    async def bad() -> int:
        raise RuntimeError("x")

    app = Application()
    app.instance(ExceptionHandler, Handler())
    set_application(app)
    assert await rescue(bad, default=1) == 1
    assert len(reported) == 1
    assert await rescue(bad, default=2, report=False) == 2
    assert len(reported) == 1
    set_application(None)


async def test_async_retry_when_predicate_false_reraises() -> None:
    calls: list[int] = []

    async def flaky() -> None:
        calls.append(1)
        raise KeyError("nope")

    with pytest.raises(KeyError):
        await retry(5, flaky, when=lambda exc: isinstance(exc, ValueError))
    assert len(calls) == 1


# --- once ---------------------------------------------------------------------
def test_once_memoizes_first_result() -> None:
    calls: list[int] = []

    @once
    def expensive() -> int:
        calls.append(1)
        return len(calls)

    assert expensive() == 1
    assert expensive() == 1
    assert len(calls) == 1


def test_once_per_instance_for_methods() -> None:
    class Svc:
        def __init__(self) -> None:
            self.n = 0

        @once
        def compute(self) -> int:
            self.n += 1
            return self.n

    a, b = Svc(), Svc()
    assert a.compute() == 1 and a.compute() == 1
    assert b.compute() == 1  # separate instance, separate memo

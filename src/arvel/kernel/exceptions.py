"""The single global exception handler (``contracts.ExceptionHandler``).

Handles uncaught exceptions across every context (HTTP, console, queue, orphan
tasks). The report/render lifecycle (errors.md): type-keyed ``reportable``/``renderable``
registration, per-exception ``context()`` merged into the report record, and
once-per-instance report de-duplication. ``render`` stays the generic fallback;
the HTTP kernel consults ``try_render`` for registered renderables first — the
callbacks' return value is opaque here so the kernel layer never imports http.

Suppression is one decision (``should_report``): the ``dont_report`` type list,
the ``ShouldntReport`` marker, and ``dont_report_when`` predicates all funnel
through it. Throttling (``Limit``/``Lottery``) runs after suppression/dedup so a
dropped report still counts as reported for dedup purposes.
"""

from __future__ import annotations

import contextlib
import random
import sys
import time
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from arvel.contracts import Logger

E = TypeVar("E", bound=BaseException)

#: Log levels a type can be pinned to via ``level()``.
_LEVELS = ("debug", "info", "warning", "error", "critical")


class ShouldntReport:
    """Marker mixin: an exception carrying it is never reported (it still renders)."""


@dataclass(frozen=True)
class Limit:
    """At most ``max_attempts`` reports of one exception type per ``per_seconds`` window."""

    max_attempts: int
    per_seconds: float = 60.0


@dataclass(frozen=True)
class Lottery:
    """Sample: report with probability ``chances / out_of``."""

    chances: int
    out_of: int

    def __post_init__(self) -> None:
        if self.out_of < 1:
            raise ValueError("Lottery out_of must be >= 1")


class ExceptionHandler:
    """Report + render uncaught exceptions; configurable via ``with_exceptions``."""

    def __init__(
        self,
        logger: Logger | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._logger = logger
        self._clock = clock
        self._dont_report: tuple[type[BaseException], ...] = ()
        self._dont_report_when: list[Callable[[BaseException], bool]] = []
        self._reportables: list[tuple[type[BaseException], Callable[[Any], bool | None]]] = []
        self._renderables: list[tuple[type[BaseException], Callable[[Any, Any], Any]]] = []
        self._levels: dict[type[BaseException], str] = {}
        self._throttlers: list[Callable[[BaseException], Limit | Lottery | None]] = []
        # keyed per throttler so two limiters with the same window never share a bucket;
        # best-effort under real threads (event-loop-safe: no await between read and write)
        self._limit_windows: dict[tuple[int, type[BaseException], float], tuple[float, int]] = {}
        self._context_providers: list[Callable[[], Mapping[str, Any]]] = []
        self._reported: weakref.WeakValueDictionary[int, BaseException] = (
            weakref.WeakValueDictionary()
        )

    def dont_report(self, *excs: type[BaseException]) -> Self:
        self._dont_report = (*self._dont_report, *excs)
        return self

    def dont_report_when(self, predicate: Callable[[BaseException], bool]) -> Self:
        """Suppress any report for which ``predicate(exc)`` is truthy (still renders)."""
        self._dont_report_when.append(predicate)
        return self

    def level(self, exc_type: type[BaseException], level: str) -> Self:
        """Log ``exc_type`` (and subclasses) at ``level`` instead of ``error``."""
        if level not in _LEVELS:
            raise ValueError(f"unknown log level {level!r} (one of {', '.join(_LEVELS)})")
        self._levels[exc_type] = level
        return self

    def throttle(self, limiter: Callable[[BaseException], Limit | Lottery | None]) -> Self:
        """Rate-limit or sample reports: ``limiter(exc)`` returns a ``Limit`` (windowed count
        per exception type), a ``Lottery`` (probability), or ``None`` for unthrottled."""
        self._throttlers.append(limiter)
        return self

    def context(self, provider: Callable[[], Mapping[str, Any]]) -> Self:
        """Merge ``provider()`` into every report's context (per-exception context wins)."""
        self._context_providers.append(provider)
        return self

    def reportable(self, exc_type: type[E], callback: Callable[[E], bool | None]) -> Self:
        """Run ``callback`` when an ``exc_type`` is reported; return ``False`` from it to
        suppress the default log write. All matches run, in
        registration order."""
        self._reportables.append((exc_type, callback))
        return self

    def renderable(self, exc_type: type[E], callback: Callable[[E, Any], Any]) -> Self:
        """Render ``exc_type`` via ``callback(exc, request)`` — first registered match whose
        result is not ``None`` wins (consulted by the HTTP kernel via ``try_render``)."""
        self._renderables.append((exc_type, callback))
        return self

    def should_report(self, exc: BaseException) -> bool:
        if isinstance(exc, (*self._dont_report, ShouldntReport)):
            return False
        for predicate in self._dont_report_when:
            try:
                if predicate(exc):
                    return False
            except Exception as hook_error:  # a broken predicate must not mask the report
                self._log_hook_failure("dont_report_when", hook_error)
        return True

    def report(self, exc: BaseException) -> None:
        if not self.should_report(exc) or not self._mark_reported(exc):
            return
        if not self._passes_throttle(exc):
            return
        write_default = True
        self_report = getattr(exc, "report", None)
        if callable(self_report):
            # the exception owns its reporting; False means "also do the default"
            try:
                if self_report() is not False:
                    write_default = False
            except Exception as hook_error:
                self._log_hook_failure("self_report", hook_error)
        for exc_type, callback in self._reportables:
            if not isinstance(exc, exc_type):
                continue
            try:
                if callback(exc) is False:
                    write_default = False
            except Exception as hook_error:  # a buggy hook must not mask the real report
                self._log_hook_failure("reportable", hook_error)
        if write_default and self._logger is not None:
            context = self._merged_context(exc)
            log = getattr(self._logger, self._level_of(exc), self._logger.error)
            log("unhandled_exception", **context, error=repr(exc), kind=type(exc).__name__)

    def try_render(self, request: Any, exc: BaseException) -> Any | None:
        """First non-``None`` result from the exception's own ``render(request)`` method, then
        matching ``renderable`` callbacks, else ``None``. Opaque to the kernel; the caller
        (HTTP kernel) converts it."""
        self_render = getattr(exc, "render", None)
        if callable(self_render):
            try:
                result = self_render(request)
            except Exception as hook_error:
                self._log_hook_failure("self_render", hook_error)
            else:
                if result is not None:
                    return result
        for exc_type, callback in self._renderables:
            if not isinstance(exc, exc_type):
                continue
            try:
                result = callback(exc, request)
            except Exception as hook_error:  # fall through to the default render
                self._log_hook_failure("renderable", hook_error)
                continue
            if result is not None:
                return result
        return None

    async def render(self, request: Any, exc: BaseException) -> Any:
        rendered = self.try_render(request, exc)
        if rendered is not None:
            return rendered
        return {"error": type(exc).__name__, "message": str(exc)}

    def render_for_console(self, output: Any, exc: BaseException) -> None:
        print(f"{type(exc).__name__}: {exc}", file=output or sys.stderr)

    def _level_of(self, exc: BaseException) -> str:
        for exc_type, level in self._levels.items():
            if isinstance(exc, exc_type):
                return level
        return "error"

    def _passes_throttle(self, exc: BaseException) -> bool:
        for limiter in self._throttlers:
            try:
                decision = limiter(exc)
            except Exception as hook_error:  # a broken limiter must not drop the report
                self._log_hook_failure("throttle", hook_error)
                continue
            if decision is None:
                continue
            if isinstance(decision, Lottery):
                # SystemRandom: sampling needs no crypto strength, but it keeps the
                # security scan clean without an annotation
                if random.SystemRandom().randrange(decision.out_of) >= decision.chances:
                    return False
                continue
            key = (id(limiter), type(exc), decision.per_seconds)
            window_start, count = self._limit_windows.get(key, (self._clock(), 0))
            now = self._clock()
            if now - window_start >= decision.per_seconds:
                window_start, count = now, 0
            if count >= decision.max_attempts:
                self._limit_windows[key] = (window_start, count)
                return False
            self._limit_windows[key] = (window_start, count + 1)
        return True

    def _mark_reported(self, exc: BaseException) -> bool:
        """True when ``exc`` has not been reported before. Identity-keyed (id → weakref) — a distinct-but-``__eq__``-equal instance still reports.
        Instances that can't be weak-referenced skip de-duplication — double-reporting beats
        silently swallowing a distinct error via id() reuse."""
        if self._reported.get(id(exc)) is exc:
            return False
        with contextlib.suppress(TypeError):
            self._reported[id(exc)] = exc
        return True

    def _log_hook_failure(self, hook: str, error: BaseException) -> None:
        if self._logger is not None:
            self._logger.error("exception_handler_hook_failed", hook=hook, error=repr(error))

    def _merged_context(self, exc: BaseException) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for provider in self._context_providers:
            try:
                merged.update(provider())
            except Exception as hook_error:  # a broken provider must not mask the report
                self._log_hook_failure("context", hook_error)
        merged.update(self._context_of(exc))  # per-exception context wins
        return merged

    @staticmethod
    def _context_of(exc: BaseException) -> Mapping[str, Any]:
        context = getattr(exc, "context", None)
        if not callable(context):
            return {}
        try:
            value = context()
        except Exception:  # a broken context() must never mask the real report
            return {}
        if not isinstance(value, dict):
            return {}
        typed = cast("dict[str, Any]", value)
        # builtin record keys always win over context-supplied ones
        return {k: v for k, v in typed.items() if k not in ("error", "kind")}

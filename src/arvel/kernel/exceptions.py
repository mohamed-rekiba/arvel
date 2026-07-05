"""The single global exception handler (``contracts.ExceptionHandler``).

Handles uncaught exceptions across every context (HTTP, console, queue, orphan
tasks). parity lifecycle (errors.md): type-keyed ``reportable``/``renderable``
registration, per-exception ``context()`` merged into the report record, and
once-per-instance report de-duplication. ``render`` stays the generic fallback;
the HTTP kernel consults ``try_render`` for registered renderables first — the
callbacks' return value is opaque here so the kernel layer never imports http.
"""

from __future__ import annotations

import contextlib
import sys
import weakref
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from arvel.contracts import Logger

E = TypeVar("E", bound=BaseException)


class ExceptionHandler:
    """Report + render uncaught exceptions; configurable via ``with_exceptions``."""

    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger
        self._dont_report: tuple[type[BaseException], ...] = ()
        self._reportables: list[tuple[type[BaseException], Callable[[Any], bool | None]]] = []
        self._renderables: list[tuple[type[BaseException], Callable[[Any, Any], Any]]] = []
        self._reported: weakref.WeakValueDictionary[int, BaseException] = (
            weakref.WeakValueDictionary()
        )

    def dont_report(self, *excs: type[BaseException]) -> Self:
        self._dont_report = (*self._dont_report, *excs)
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
        return not isinstance(exc, self._dont_report)

    def report(self, exc: BaseException) -> None:
        if not self.should_report(exc) or not self._mark_reported(exc):
            return
        write_default = True
        for exc_type, callback in self._reportables:
            if not isinstance(exc, exc_type):
                continue
            try:
                if callback(exc) is False:
                    write_default = False
            except Exception as hook_error:  # a buggy hook must not mask the real report
                self._log_hook_failure("reportable", hook_error)
        if write_default and self._logger is not None:
            context = self._context_of(exc)
            self._logger.error(
                "unhandled_exception", **context, error=repr(exc), kind=type(exc).__name__
            )

    def try_render(self, request: Any, exc: BaseException) -> Any | None:
        """First non-``None`` result from a matching ``renderable`` callback, else ``None``.
        The result is opaque to the kernel; the caller (HTTP kernel) converts it."""
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

    def _mark_reported(self, exc: BaseException) -> bool:
        """True when ``exc`` has not been reported before. Identity-keyed (id → weakref), matching
        the spl_object_id map — a distinct-but-``__eq__``-equal instance still reports.
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

"""The single global exception handler (``contracts.ExceptionHandler``).

Handles uncaught exceptions across every context (HTTP, console, queue, orphan
tasks). Laravel-parity lifecycle (errors.md): type-keyed ``reportable``/``renderable``
registration, per-exception ``context()`` merged into the report record, and
once-per-instance report de-duplication. ``render`` stays the generic fallback;
the HTTP kernel consults ``try_render`` for registered renderables first — the
callbacks' return value is opaque here so the kernel layer never imports http.
"""

from __future__ import annotations

import sys
import weakref
from typing import TYPE_CHECKING, Any, TypeVar, cast

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
        self._reported: weakref.WeakSet[BaseException] = weakref.WeakSet()

    def dont_report(self, *excs: type[BaseException]) -> ExceptionHandler:
        self._dont_report = (*self._dont_report, *excs)
        return self

    def reportable(
        self, exc_type: type[E], callback: Callable[[E], bool | None]
    ) -> ExceptionHandler:
        """Run ``callback`` when an ``exc_type`` is reported; return ``False`` from it to
        suppress the default log write (Laravel's ``return false``). All matches run, in
        registration order."""
        self._reportables.append((exc_type, callback))
        return self

    def renderable(self, exc_type: type[E], callback: Callable[[E, Any], Any]) -> ExceptionHandler:
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
            if isinstance(exc, exc_type) and callback(exc) is False:
                write_default = False
        if write_default and self._logger is not None:
            context = self._context_of(exc)
            self._logger.error(
                "unhandled_exception", **context, error=repr(exc), kind=type(exc).__name__
            )

    def try_render(self, request: Any, exc: BaseException) -> Any | None:
        """First non-``None`` result from a matching ``renderable`` callback, else ``None``.
        The result is opaque to the kernel; the caller (HTTP kernel) converts it."""
        for exc_type, callback in self._renderables:
            if isinstance(exc, exc_type):
                result = callback(exc, request)
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
        """True when ``exc`` has not been reported before. Instances that can't be weak-referenced
        (e.g. ``__slots__`` without ``__weakref__``) skip de-duplication — double-reporting beats
        silently swallowing a distinct error via id() reuse."""
        try:
            if exc in self._reported:
                return False
            self._reported.add(exc)
        except TypeError:
            return True
        return True

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

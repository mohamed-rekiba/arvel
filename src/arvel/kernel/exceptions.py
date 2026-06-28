"""The single global exception handler (``contracts.ExceptionHandler``).

Handles uncaught exceptions across every context (HTTP, console, queue, orphan
tasks): ``report()`` logs (unless suppressed via ``dont_report``), and renders
content-appropriately. The content-negotiated HTTP render is overridden in
Phase 4; here ``render`` returns a generic payload. Grounded in knowledge/port/03.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.contracts import Logger


class ExceptionHandler:
    """Report + render uncaught exceptions; configurable via ``with_exceptions``."""

    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger
        self._dont_report: tuple[type[BaseException], ...] = ()

    def dont_report(self, *excs: type[BaseException]) -> ExceptionHandler:
        self._dont_report = (*self._dont_report, *excs)
        return self

    def should_report(self, exc: BaseException) -> bool:
        return not isinstance(exc, self._dont_report)

    def report(self, exc: BaseException) -> None:
        if self.should_report(exc) and self._logger is not None:
            self._logger.error("unhandled_exception", error=repr(exc), kind=type(exc).__name__)

    async def render(self, request: Any, exc: BaseException) -> Any:
        # Generic payload; the HTTP kernel installs a content-negotiated render in Phase 4.
        return {"error": type(exc).__name__, "message": str(exc)}

    def render_for_console(self, output: Any, exc: BaseException) -> None:
        print(f"{type(exc).__name__}: {exc}", file=output or sys.stderr)

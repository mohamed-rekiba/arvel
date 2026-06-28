"""Event-driven boot / shutdown reporter.

Subscribes to the application **hook bus** (``booting``/``booted``/``terminating``)
and reports startup/shutdown with per-phase timings — decoupled from boot
internals. Raw ANSI output (no ``rich``, per the startup NFR). Attached on the
server/worker path (the lifespan), never on the fast T0 CLI path. Verbosity:
``quiet`` | ``summary`` | ``verbose``. Grounded in knowledge/port/03 (boot report).
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from arvel.kernel.application import Application


class BootReporter:
    def __init__(
        self, app: Application, *, level: str = "summary", out: TextIO | None = None
    ) -> None:
        self.app = app
        self.level = level
        self.out: TextIO = out if out is not None else sys.stderr
        self._timings: dict[str, float] = {}

    def register(self) -> None:
        self.app.on("booting", self._on_booting)
        self.app.on("booted", self._on_booted)
        self.app.on("terminating", self._on_terminating)

    def _on_booting(self, _app: Application) -> None:
        self._timings["boot_start"] = time.perf_counter()

    def _on_booted(self, app: Application) -> None:
        if self.level == "quiet":
            return
        start = self._timings.get("boot_start")
        ms = (time.perf_counter() - start) * 1000 if start is not None else 0.0
        booted = app.booted_provider_count
        deferred = len(app.registered_provider_types) - booted
        # report what actually booted; note deferred providers (registered, not yet booted) separately
        suffix = f" (+{deferred} deferred)" if deferred > 0 else ""
        env = app.config("app.env", "local")
        self._write(
            f"{self._paint('✓ arvel', '35')} ready in {ms:.0f} ms · "
            f"{booted} providers{suffix} · env={env}"
        )

    def _on_terminating(self, _app: Application) -> None:
        if self.level == "quiet":
            return
        self._write(f"{self._paint('↘ arvel', '35')} shutting down gracefully")

    def _paint(self, text: str, code: str) -> str:
        """Wrap ``text`` in an ANSI color only when writing to a TTY — so piped/redirected/CI output
        (a non-tty) stays clean of escape codes."""
        if hasattr(self.out, "isatty") and self.out.isatty():
            return f"\033[{code}m{text}\033[0m"
        return text

    def _write(self, line: str) -> None:
        print(line, file=self.out)

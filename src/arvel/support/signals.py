"""arvel.support.signals — one shared context manager for scoped event-loop signal traps.

``loop.add_signal_handler``/``remove_signal_handler`` is the only public asyncio API for reacting
to SIGTERM/SIGINT without reaching into private loop state (DR-0050: asyncio exposes no getter for
"the handler that was there before", so restore-on-exit means remove-to-default, not
restore-previous). This wraps install-on-enter/remove-on-exit around it so the worker, the
scheduler, and ``Command.trap`` (E16) share one mechanism instead of three copies of the same
suppress-and-loop block.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Callable, Generator, Mapping
from typing import Any


@contextlib.contextmanager
def signal_traps(handlers: Mapping[signal.Signals, Callable[[], Any]]) -> Generator[None]:
    """Install each ``sig: handler`` on the running loop for the life of this scope; remove
    exactly those on exit, leaving the loop in its pre-scope ("no handler") state — not restored
    to whatever was there before, since asyncio has no getter for that (DR-0050).

    Degrades to a silent no-op per signal, never a crash, when installation isn't possible:
    ``NotImplementedError`` (Windows), ``RuntimeError`` (no running loop / loop setup failure —
    also what a non-main-thread loop raises on this project's asyncio), and ``ValueError`` (the
    non-main-thread ``set_wakeup_fd`` failure on asyncio builds that surface it directly rather
    than wrapping it in ``RuntimeError`` — the ``Cli.call``-from-a-request thread-bridge path,
    ``console/kernel.py:_run_to_completion``, runs the command on a fresh loop in a worker
    thread). Removes only what it installed — no blanket clear of unrelated handlers.
    """
    installed: list[signal.Signals] = []
    loop: asyncio.AbstractEventLoop | None = None
    with contextlib.suppress(RuntimeError):
        loop = asyncio.get_running_loop()
    if loop is not None:
        for sig, handler in handlers.items():
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.add_signal_handler(sig, handler)
                installed.append(sig)
    try:
        yield
    finally:
        if loop is not None:
            for sig in installed:
                with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                    loop.remove_signal_handler(sig)


__all__ = ["signal_traps"]

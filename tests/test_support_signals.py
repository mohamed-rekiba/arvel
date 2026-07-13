"""`signal_traps` — the one shared install-on-enter/remove-on-exit context manager E16 extracts
from the worker/scheduler's inline blocks so `Command.trap` (and they) share a single mechanism.
Restore is remove-to-default (DR-0050), not restore-previous — asserted via `signal.getsignal`
rather than a second real SIGTERM, which would hit the (now-default) terminate action."""

from __future__ import annotations

import asyncio
import os
import signal
import threading

import pytest

from arvel.support.signals import signal_traps


async def test_installs_invokes_and_removes_to_default_on_exit() -> None:
    hit = asyncio.Event()
    with signal_traps({signal.SIGTERM: hit.set}):
        assert signal.getsignal(signal.SIGTERM) != signal.SIG_DFL  # installed
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(hit.wait(), timeout=2)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL  # removed-to-default, not leaked


async def test_installs_multiple_signals_and_removes_to_default() -> None:
    pre_int = signal.getsignal(signal.SIGINT)
    with signal_traps({signal.SIGTERM: lambda: None, signal.SIGINT: lambda: None}):
        assert signal.getsignal(signal.SIGTERM) != signal.SIG_DFL
        assert signal.getsignal(signal.SIGINT) != pre_int
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    # remove-to-default (DR-0050), not restore-previous: asyncio always resets SIGINT to its own
    # default_int_handler on remove, regardless of what was installed before the scope.
    assert signal.getsignal(signal.SIGINT) == signal.default_int_handler


async def test_removes_only_what_it_installed_leaves_untouched_signal_alone() -> None:
    # only SIGTERM is handed to the scope; SIGINT's state must be untouched by exit.
    pre_int = signal.getsignal(signal.SIGINT)
    with signal_traps({signal.SIGTERM: lambda: None}):
        pass
    assert signal.getsignal(signal.SIGINT) == pre_int


def test_no_running_loop_degrades_to_a_silent_no_op() -> None:
    # called synchronously, outside any event loop — must not raise.
    with signal_traps({signal.SIGTERM: lambda: None}):
        pass


def test_off_main_thread_degrades_to_a_silent_no_op() -> None:
    # the Cli.call-from-a-request thread-bridge path (console/kernel.py:_run_to_completion) runs
    # the command on a fresh loop in a worker thread, where add_signal_handler can't install.
    errors: list[BaseException] = []

    def worker() -> None:
        async def main() -> None:
            with signal_traps({signal.SIGTERM: lambda: None}):
                pass

        try:
            asyncio.run(main())
        except BaseException as exc:  # pragma: no cover - would only fire on a real regression
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)
    assert errors == []


async def test_restores_even_when_the_body_raises() -> None:
    # the contextmanager's own finally must remove the handler on an exception, not only on a
    # clean exit — otherwise a command that raises mid-run would leak its trap.
    with pytest.raises(RuntimeError, match="boom"), signal_traps({signal.SIGTERM: lambda: None}):
        assert signal.getsignal(signal.SIGTERM) != signal.SIG_DFL
        raise RuntimeError("boom")
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL  # removed despite the raise

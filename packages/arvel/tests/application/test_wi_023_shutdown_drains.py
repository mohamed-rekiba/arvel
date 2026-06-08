"""Shutdown drains every provider even when one teardown raises.

A failing provider used to abort the reverse-shutdown loop, stranding the
providers after it — most importantly the DB provider, which never got to
dispose its engine. Shutdown now drains all of them, flips `_booted`, then
surfaces the first failure.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def test_failing_provider_does_not_strand_later_teardowns(tmp_path: Path) -> None:
    from arvel import Application, ServiceProvider
    from arvel.application.errors import ShutdownError

    torn_down: list[str] = []

    # Registration order: Early then Bad. Reverse shutdown hits Bad first, so a
    # naive fail-fast would skip Early entirely.
    class Early(ServiceProvider):
        async def shutdown(self) -> None:
            torn_down.append("early")

    class Bad(ServiceProvider):
        async def shutdown(self) -> None:
            raise RuntimeError("teardown failure")

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([Early, Bad])
        .create()
    )
    asyncio.run(app.boot())

    with pytest.raises(ShutdownError) as excinfo:
        asyncio.run(app.shutdown())

    assert excinfo.value.provider is Bad
    assert "early" in torn_down


def test_shutdown_clears_booted_even_on_failure(tmp_path: Path) -> None:
    from arvel import Application, ServiceProvider
    from arvel.application.errors import ShutdownError

    class Bad(ServiceProvider):
        async def shutdown(self) -> None:
            raise RuntimeError("teardown failure")

    app = Application.configure(tmp_path).with_environment("testing").with_providers([Bad]).create()
    asyncio.run(app.boot())

    with pytest.raises(ShutdownError):
        asyncio.run(app.shutdown())

    # A second shutdown is a no-op — the first one flipped the flag despite raising.
    asyncio.run(app.shutdown())

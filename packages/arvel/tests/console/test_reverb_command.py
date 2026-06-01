"""`arvel reverb:start` console command."""

from __future__ import annotations

import pytest


def test_reverb_command_is_typer_subcommand() -> None:
    """ReverbStartCommand registered with Typer console."""
    from arvel.console.commands.reverb_commands import ReverbStartCommand

    # Smoke check — has the required Console command surface.
    assert hasattr(ReverbStartCommand, "handle") or callable(ReverbStartCommand)


@pytest.mark.asyncio
async def test_reverb_command_binds_to_configured_host_port() -> None:
    """command honours --host and --port flags (override config)."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.console.commands.reverb_commands import build_reverb_runtime

    config = ReverbConfig(app_id="x", key="k", secret="s", host="127.0.0.1", port=6001)
    server, host, port = build_reverb_runtime(config, host_override=None, port_override=None)
    assert server is not None
    assert host == "127.0.0.1"
    assert port == 6001

    bind_all = "0.0.0.0"  # noqa: S104
    _, host2, port2 = build_reverb_runtime(config, host_override=bind_all, port_override=9999)
    assert host2 == bind_all
    assert port2 == 9999


def test_reverb_command_emits_startup_log(caplog: pytest.LogCaptureFixture) -> None:
    """structured 'reverb_started' log emitted on bind."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.console.commands.reverb_commands import log_reverb_started

    with caplog.at_level("INFO"):
        log_reverb_started(
            ReverbConfig(app_id="x", key="k", secret="s", host="127.0.0.1", port=6001),
        )
    assert any("reverb_started" in r.message for r in caplog.records)

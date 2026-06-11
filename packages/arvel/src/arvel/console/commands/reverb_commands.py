"""`arvel reverb:start` console command."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import typer

from arvel.console import Command, Context
from arvel.console._t import Option

if TYPE_CHECKING:
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.redis_bus import RedisBus
    from arvel.reverb.server import ReverbServer

logger = logging.getLogger(__name__)


class ReverbStartCommand(Command):
    """Typer command class for ``arvel reverb:start``."""

    name = "reverb:start"
    help = "Start the Reverb WebSocket server."

    def register(self, app: typer.Typer) -> None:
        def _callback(
            host: str | None = Option(None, "--host", help="Override REVERB_HOST."),
            port: int | None = Option(None, "--port", help="Override REVERB_PORT."),
        ) -> None:
            from arvel.console import _async as _arvel_async

            # ReverbConfig fields come from env vars via pydantic-settings.
            config = _load_reverb_config_from_env()
            server, bind_host, bind_port = build_reverb_runtime(config, host, port)
            log_reverb_started(config)
            _arvel_async.schedule_async(server.serve(bind_host, bind_port))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        # Behavior lives in register() via the Typer callback; handle() is
        # never invoked because register() is overridden.
        raise NotImplementedError


def _load_reverb_config_from_env() -> ReverbConfig:
    """Materialize ReverbConfig from env vars.

    Pydantic-settings populates fields from env, so the runtime call has no
    positional args even though the dataclass-like signature shows required ones.
    """
    from arvel.broadcasting.config import ReverbConfig as _ReverbConfig

    return _ReverbConfig.model_validate({})


def build_reverb_runtime(
    config: ReverbConfig,
    host_override: str | None,
    port_override: int | None,
) -> tuple[ReverbServer, str, int]:
    """Construct the ReverbServer + resolve effective host/port.

    With ``REVERB_SCALING_ENABLED`` set, wire a RedisBus so this process picks
    up broadcasts published by other processes.
    """
    from arvel.reverb.server import ReverbServer

    server = ReverbServer(config=config, redis_bus=_build_redis_bus(config))
    host = host_override if host_override is not None else config.host
    port = port_override if port_override is not None else config.port
    return server, host, port


def _build_redis_bus(config: ReverbConfig) -> RedisBus | None:
    """Return a RedisBus when scaling is on; None for single-process mode."""
    if not config.scaling_enabled:
        return None
    import importlib

    try:
        aioredis = importlib.import_module("redis.asyncio")
    except ImportError as exc:
        msg = (
            "REVERB_SCALING_ENABLED requires arvel[redis]. Install with: pip install 'arvel[redis]'"
        )
        raise RuntimeError(msg) from exc
    from arvel.reverb.redis_bus import AsyncRedis, RedisBus

    # Default localhost client — same connection source as RedisBroadcaster.
    client = cast("AsyncRedis", aioredis.Redis())
    return RedisBus(redis=client, config=config)


def log_reverb_started(config: ReverbConfig) -> None:
    """Emit the ``reverb_started`` structured event."""
    logger.info(
        "reverb_started host=%s port=%d app_id=%s",
        config.host,
        config.port,
        config.app_id,
    )


__all__ = ["ReverbStartCommand", "build_reverb_runtime", "log_reverb_started"]

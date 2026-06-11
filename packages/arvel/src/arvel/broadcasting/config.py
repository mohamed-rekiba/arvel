"""Broadcasting + Reverb configuration."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import ConfigDict, Field, HttpUrl
from pydantic_settings import SettingsConfigDict

from arvel.config.settings import ArvelSettings


class BroadcastDriver(StrEnum):
    """Allowed values for ``BroadcastConfig.default``."""

    LOG = "log"
    NULL = "null"
    REDIS_PUBSUB = "redis-pubsub"
    PUSHER = "pusher"


class BroadcastConfig(ArvelSettings):
    """Broadcasting settings — picks the default driver and exposes the auth endpoint.

    Env vars (auto-prefixed ``BROADCASTING_``):

    - ``BROADCASTING_DEFAULT``        (default: ``null``)
    - ``BROADCASTING_AUTH_ENDPOINT``  (default: ``/broadcasting/auth``)
    """

    # match_prefix is required with extra="forbid": a shared .env at the CWD
    # carries unrelated keys (APP_KEY, DB_*, ...) that would otherwise trip the
    # forbid check on every load.
    model_config = SettingsConfigDict(
        env_prefix="BROADCASTING_",
        extra="forbid",
        dotenv_filtering="match_prefix",
    )
    __config_path__ = "broadcasting"

    default: BroadcastDriver = BroadcastDriver.NULL
    auth_endpoint: str = "/broadcasting/auth"


class ReverbConfig(ArvelSettings):
    """Reverb WS server settings.

    Env vars (auto-prefixed ``REVERB_``):

    - ``REVERB_APP_ID``                (required)
    - ``REVERB_KEY``                   (required)
    - ``REVERB_SECRET``                (required)
    - ``REVERB_HOST``                  (default: ``127.0.0.1``)
    - ``REVERB_PORT``                  (default: 8080)
    - ``REVERB_ACTIVITY_TIMEOUT``      (default: 120 seconds; 30..3600)
    - ``REVERB_MAX_CONNECTIONS_PER_IP``(default: 100; 1..10000)
    - ``REVERB_ALLOWED_ORIGINS``       (default: [] = same-origin only; ``["*"]`` opts into any)
    - ``REVERB_TRUSTED_PROXIES``       (default: []; only then ``X-Forwarded-For`` is honoured)
    - ``REVERB_SCALING_ENABLED``       (default: false; true PSUBSCRIBEs to the Redis fan-out)
    """

    model_config = SettingsConfigDict(
        env_prefix="REVERB_",
        extra="forbid",
        dotenv_filtering="match_prefix",
    )

    app_id: str
    key: str
    secret: str
    host: str = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=65535)] = 8080
    activity_timeout: Annotated[int, Field(ge=30, le=3600)] = 120
    max_connections_per_ip: Annotated[int, Field(ge=1, le=10000)] = 100
    allowed_origins: list[HttpUrl] | list[str] = []
    trusted_proxies: list[str] = []
    # Multi-process fan-out: when true, reverb:start PSUBSCRIBEs to the same Redis
    # channels RedisBroadcaster publishes on. Off by default so single-process
    # dev needs no Redis. Mirrors Laravel's REVERB_SCALING_ENABLED.
    scaling_enabled: bool = False


# Keep both pydantic ConfigDict and SettingsConfigDict references alive for
# the type checker — `ConfigDict` is used implicitly through SettingsConfigDict.
_ = ConfigDict


__all__ = ["BroadcastConfig", "BroadcastDriver", "ReverbConfig"]

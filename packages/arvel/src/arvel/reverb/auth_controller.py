"""BroadcastAuthController — HTTP-side channel-auth endpoint (FR-013-023, NFR-013-008)."""

from __future__ import annotations

import json
import logging

from arvel.broadcasting.channels import ChannelRegistry, validate_channel_name
from arvel.broadcasting.config import BroadcastConfig, ReverbConfig
from arvel.broadcasting.exceptions import BroadcastAuthError
from arvel.reverb.auth import sign_channel_auth

logger = logging.getLogger(__name__)


class BroadcastAuthController:
    """Resolves a private/presence channel subscription against the registry.

    Returns the signed payload Pusher clients expect. On any rejection raises
    ``BroadcastAuthError`` — the error message MUST NOT include the secret
    (SEC-013-007).
    """

    def __init__(
        self,
        *,
        registry: ChannelRegistry,
        config: BroadcastConfig,
        reverb: ReverbConfig,
    ) -> None:
        self._registry: ChannelRegistry = registry
        self._config: BroadcastConfig = config
        self._reverb: ReverbConfig = reverb

    async def handle(
        self,
        *,
        socket_id: str,
        channel: str,
        user: object | None,
    ) -> dict[str, str]:
        if user is None:
            self._reject("unauthenticated", socket_id, channel)
        validate_channel_name(channel)
        result = await self._registry.authorize(channel, user=user)
        if not result:
            self._reject("forbidden", socket_id, channel)

        if isinstance(result, dict):
            channel_data = json.dumps(result)
            auth = sign_channel_auth(
                secret=self._reverb.secret,
                key=self._reverb.key,
                socket_id=socket_id,
                channel=channel,
                channel_data=channel_data,
            )
            return {"auth": auth, "channel_data": channel_data}

        auth = sign_channel_auth(
            secret=self._reverb.secret,
            key=self._reverb.key,
            socket_id=socket_id,
            channel=channel,
        )
        return {"auth": auth}

    @staticmethod
    def _reject(reason: str, socket_id: str, channel: str) -> None:
        logger.warning(
            "broadcast_auth_rejected reason=%s socket_id=%s channel=%s",
            reason,
            socket_id,
            channel,
        )
        raise BroadcastAuthError(f"Channel authorization rejected ({reason})")


__all__ = ["BroadcastAuthController"]

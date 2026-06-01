"""LogBroadcaster — emit a structured log; never send anything over the wire."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence

logger = logging.getLogger(__name__)


class LogBroadcaster:
    """Dev driver. Logs ``broadcast_emitted`` with channel + event + payload keys.

    Per payload **values** are NOT logged — only keys.
    """

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        record: dict[str, object] = {
            "event": "broadcast_emitted",
            "channels": list(channels),
            "event_name": event,
            "payload_keys": sorted(payload.keys()),
            "except_socket_id": except_socket_id,
        }
        logger.info("broadcast_emitted %s", json.dumps(record))


__all__ = ["LogBroadcaster"]

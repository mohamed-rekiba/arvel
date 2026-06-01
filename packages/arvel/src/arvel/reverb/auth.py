"""Channel-auth HMAC-SHA256 signature scheme."""

from __future__ import annotations

import hashlib
import hmac


def sign_channel_auth(
    *,
    secret: str,
    key: str,
    socket_id: str,
    channel: str,
    channel_data: str | None = None,
) -> str:
    """Return the ``<key>:<hex-signature>`` token expected by Pusher clients."""
    if not secret:
        msg = "secret must be a non-empty string"
        raise ValueError(msg)
    payload = f"{socket_id}:{channel}"
    if channel_data is not None:
        payload = f"{payload}:{channel_data}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{key}:{signature}"


def verify_channel_auth(
    *,
    auth: str,
    secret: str,
    key: str,
    socket_id: str,
    channel: str,
    channel_data: str | None = None,
) -> bool:
    """Constant-time check: returns True iff ``auth`` is a valid signature."""
    expected = sign_channel_auth(
        secret=secret,
        key=key,
        socket_id=socket_id,
        channel=channel,
        channel_data=channel_data,
    )
    return hmac.compare_digest(expected, auth)


__all__ = ["sign_channel_auth", "verify_channel_auth"]

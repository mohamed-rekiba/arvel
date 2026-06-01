"""Channel auth signature scheme (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest


def test_sign_channel_auth_private_channel() -> None:
    """private signature = HMAC-SHA256(secret, "<socket_id>:<channel>")."""
    from arvel.reverb.auth import sign_channel_auth

    secret = "the-secret"
    socket_id = "123.456"
    channel = "private-user.5"
    expected = hmac.new(
        secret.encode(),
        f"{socket_id}:{channel}".encode(),
        hashlib.sha256,
    ).hexdigest()

    auth = sign_channel_auth(secret=secret, key="the-key", socket_id=socket_id, channel=channel)
    # Auth format is "{key}:{signature}"
    assert auth == f"the-key:{expected}"


def test_sign_channel_auth_presence_channel_includes_channel_data() -> None:
    """presence signature = HMAC over "<socket>:<channel>:<channel_data>"."""
    from arvel.reverb.auth import sign_channel_auth

    secret = "s"
    socket_id = "1.2"
    channel = "presence-room.7"
    channel_data = json.dumps({"user_id": "u-42", "user_info": {"name": "A"}})
    expected = hmac.new(
        secret.encode(),
        f"{socket_id}:{channel}:{channel_data}".encode(),
        hashlib.sha256,
    ).hexdigest()
    auth = sign_channel_auth(
        secret=secret,
        key="k",
        socket_id=socket_id,
        channel=channel,
        channel_data=channel_data,
    )
    assert auth == f"k:{expected}"


def test_verify_channel_auth_accepts_valid_signature() -> None:
    """verify_channel_auth accepts a correctly signed token."""
    from arvel.reverb.auth import sign_channel_auth, verify_channel_auth

    auth = sign_channel_auth(secret="s", key="k", socket_id="1.2", channel="private-x.1")
    assert verify_channel_auth(
        auth=auth,
        secret="s",
        key="k",
        socket_id="1.2",
        channel="private-x.1",
    )


def test_verify_channel_auth_rejects_tampered_signature() -> None:
    """tampered signature is rejected."""
    from arvel.reverb.auth import verify_channel_auth

    assert not verify_channel_auth(
        auth="k:0123456789abcdef" * 4,
        secret="s",
        key="k",
        socket_id="1.2",
        channel="private-x.1",
    )


def test_verify_channel_auth_uses_compare_digest() -> None:
    """implementation uses hmac.compare_digest (no early-return on mismatch)."""
    import inspect

    from arvel.reverb import auth as auth_module

    source = inspect.getsource(auth_module)
    assert "compare_digest" in source, "verify_channel_auth must use hmac.compare_digest"


def test_verify_channel_auth_rejects_mismatched_key() -> None:
    from arvel.reverb.auth import sign_channel_auth, verify_channel_auth

    auth = sign_channel_auth(secret="s", key="key-A", socket_id="1.2", channel="private-x.1")
    # Different key in verification
    assert not verify_channel_auth(
        auth=auth,
        secret="s",
        key="key-B",
        socket_id="1.2",
        channel="private-x.1",
    )


def test_sign_rejects_empty_secret() -> None:
    """Defensive: signing with empty secret raises ValueError."""
    from arvel.reverb.auth import sign_channel_auth

    with pytest.raises(ValueError, match="secret"):
        sign_channel_auth(secret="", key="k", socket_id="1.2", channel="private-x.1")

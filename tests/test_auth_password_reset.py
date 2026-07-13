"""PasswordBroker — single-use + throttled + expiring password reset (A6 fix).

Replaces the old stateless signed-token flow: the token row is deleted on every terminal outcome
(success or expiry), so a replay never succeeds even inside the original TTL."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from arvel.auth.password_reset import (
    PasswordBroker,
    PasswordReset,
    PasswordResetRequested,
    PasswordResetStatus,
    PasswordResetToken,
)
from arvel.auth.remember import RememberToken, issue_remember_token, recall_remember_token
from arvel.database import ConnectionResolver


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def dispatch(self, event: Any) -> list[Any]:
        self.events.append(event)
        return []


class _User:
    def __init__(self, uid: int, email: str) -> None:
        self.id = uid
        self.email = email
        self.password = "old-hash"

    def get_auth_identifier(self) -> int:
        return self.id


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    PasswordResetToken.set_connection(db)
    RememberToken.set_connection(db)
    await db.execute(sa.schema.CreateTable(PasswordResetToken.__table__))
    await db.execute(sa.schema.CreateTable(RememberToken.__table__))
    return db


def _lookup_for(users: dict[str, _User]) -> Any:
    async def _lookup(email: str) -> _User | None:
        return users.get(email)

    return _lookup


def _set_password(user: _User, new_password: str) -> None:
    user.password = f"hash({new_password})"


async def _sent_token(dispatcher: _RecordingDispatcher) -> str:
    requested = next(e for e in dispatcher.events if isinstance(e, PasswordResetRequested))
    return str(requested.token)


async def test_send_reset_link_success_dispatches_event_and_stores_only_the_hash() -> None:
    db = await _db()
    try:
        user = _User(1, "ada@example.com")
        dispatcher = _RecordingDispatcher()
        broker = PasswordBroker(_lookup_for({"ada@example.com": user}), dispatcher=dispatcher)

        status = await broker.send_reset_link("ada@example.com")
        assert status is PasswordResetStatus.RESET_SUCCESS

        record = await PasswordResetToken.where(email="ada@example.com").first()
        assert record is not None
        token = await _sent_token(dispatcher)
        assert record.token_hash != token  # only the HASH is stored, never the plaintext
    finally:
        await db.dispose()


async def test_send_reset_link_unknown_email_is_invalid_user() -> None:
    db = await _db()
    try:
        broker = PasswordBroker(_lookup_for({}))
        assert (
            await broker.send_reset_link("nobody@example.com") is PasswordResetStatus.INVALID_USER
        )
    finally:
        await db.dispose()


async def test_send_reset_link_throttled_within_the_window() -> None:
    db = await _db()
    try:
        user = _User(1, "ada@example.com")
        broker = PasswordBroker(_lookup_for({"ada@example.com": user}), throttle_seconds=3600)

        first = await broker.send_reset_link("ada@example.com")
        assert first is PasswordResetStatus.RESET_SUCCESS

        second = await broker.send_reset_link("ada@example.com")  # too soon
        assert second is PasswordResetStatus.RESET_THROTTLED
    finally:
        await db.dispose()


async def test_reset_success_is_single_use_rotates_remember_and_fires_event() -> None:
    db = await _db()
    try:
        user = _User(1, "ada@example.com")
        old_remember = await issue_remember_token(user.id)

        dispatcher = _RecordingDispatcher()
        broker = PasswordBroker(_lookup_for({"ada@example.com": user}), dispatcher=dispatcher)

        assert await broker.send_reset_link("ada@example.com") is PasswordResetStatus.RESET_SUCCESS
        token = await _sent_token(dispatcher)

        status = await broker.reset("ada@example.com", token, "new-secret", _set_password)
        assert status is PasswordResetStatus.RESET_SUCCESS
        assert user.password == "hash(new-secret)"

        # single-use: the row is gone, so the SAME token again is INVALID_TOKEN — even inside the TTL
        replay = await broker.reset("ada@example.com", token, "another-secret", _set_password)
        assert replay is PasswordResetStatus.INVALID_TOKEN

        # remember token rotated (revoked) on a successful reset — the old one no longer authenticates
        assert await recall_remember_token(old_remember) is None

        assert any(isinstance(e, PasswordReset) for e in dispatcher.events)
    finally:
        await db.dispose()


async def test_reset_wrong_token_is_invalid_token() -> None:
    db = await _db()
    try:
        user = _User(1, "ada@example.com")
        broker = PasswordBroker(_lookup_for({"ada@example.com": user}))
        await broker.send_reset_link("ada@example.com")

        status = await broker.reset(
            "ada@example.com", "not-the-real-token", "new-secret", _set_password
        )
        assert status is PasswordResetStatus.INVALID_TOKEN
    finally:
        await db.dispose()


async def test_reset_unknown_email_is_invalid_user() -> None:
    db = await _db()
    try:
        broker = PasswordBroker(_lookup_for({}))
        status = await broker.reset("nobody@example.com", "whatever", "new-secret", _set_password)
        assert status is PasswordResetStatus.INVALID_USER
    finally:
        await db.dispose()


async def test_reset_no_token_sent_is_invalid_token() -> None:
    db = await _db()
    try:
        user = _User(1, "ada@example.com")
        broker = PasswordBroker(_lookup_for({"ada@example.com": user}))
        status = await broker.reset("ada@example.com", "whatever", "new-secret", _set_password)
        assert status is PasswordResetStatus.INVALID_TOKEN
    finally:
        await db.dispose()


async def test_reset_expired_token_is_expired_and_cleans_up() -> None:
    db = await _db()
    try:
        user = _User(1, "ada@example.com")
        dispatcher = _RecordingDispatcher()
        sender = PasswordBroker(_lookup_for({"ada@example.com": user}), dispatcher=dispatcher)
        await sender.send_reset_link("ada@example.com")
        token = await _sent_token(dispatcher)

        expired_view = PasswordBroker(_lookup_for({"ada@example.com": user}), ttl_seconds=-1)
        status = await expired_view.reset("ada@example.com", token, "new-secret", _set_password)
        assert status is PasswordResetStatus.EXPIRED

        # expired row was cleaned up — even a (hypothetically) correct token now reads INVALID_TOKEN
        assert (await PasswordResetToken.where(email="ada@example.com").first()) is None
    finally:
        await db.dispose()


async def test_reset_callback_may_be_sync_or_async() -> None:
    db = await _db()
    try:
        user = _User(1, "ada@example.com")
        dispatcher = _RecordingDispatcher()
        broker = PasswordBroker(_lookup_for({"ada@example.com": user}), dispatcher=dispatcher)
        await broker.send_reset_link("ada@example.com")
        token = await _sent_token(dispatcher)

        async def _async_set(u: _User, new_password: str) -> None:
            u.password = f"async-hash({new_password})"

        status = await broker.reset("ada@example.com", token, "s3cret", _async_set)
        assert status is PasswordResetStatus.RESET_SUCCESS
        assert user.password == "async-hash(s3cret)"
    finally:
        await db.dispose()

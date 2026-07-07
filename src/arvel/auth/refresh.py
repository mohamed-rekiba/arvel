"""arvel.auth.refresh — rotating refresh tokens with reuse detection.

A refresh token is exchanged for a new access token; on each exchange the presented token is
revoked and a fresh one issued (rotation), so a leaked refresh token is single-use. Only the
SHA-256 hash is stored. **Reuse detection:** presenting an already-rotated (revoked) token is a
theft signal — the legitimate client and an attacker both hold one — so the entire token family
for that user is revoked, forcing a fresh login. Grounded in knowledge/port/15 + DR-0014.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, ClassVar

from arvel.database import Model


class RefreshToken(Model):
    """A rotating refresh token bound to a user (``tokenable_id``).

    Invariant: rows are **soft-revoked** (``revoked`` flag), never deleted — this keeps the
    atomic-claim + follow-up read in ``rotate_refresh_token`` consistent and preserves reuse detection
    (a replayed, already-revoked token is still found).
    """

    __table_name__ = "refresh_tokens"
    __fields__: ClassVar[dict[str, Any]] = {"token": str, "tokenable_id": int, "revoked": bool}
    __fillable__: ClassVar[list[str]] = ["token", "tokenable_id", "revoked"]


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


async def issue_refresh_token(tokenable_id: int) -> str:
    """Issue a new refresh token for a user; returns the plaintext (store the hash only)."""
    plaintext = secrets.token_hex(32)
    await RefreshToken.create(token=_hash(plaintext), tokenable_id=tokenable_id, revoked=False)
    return plaintext


async def revoke_all_refresh_tokens(tokenable_id: int) -> None:
    """Revoke every refresh token belonging to a user (e.g. on logout or reuse detection)."""
    await RefreshToken.where(tokenable_id=tokenable_id).update({"revoked": True})


async def rotate_refresh_token(plaintext: str) -> tuple[str, int] | None:
    """Validate + rotate: revoke the presented token and issue a fresh one.

    Returns ``(new_plaintext, tokenable_id)``, or ``None`` when the exchange is rejected.

    Reuse detection (DR-0014): a token that was already rotated is still found (the reuse lookup is
    not filtered on ``revoked``). Presenting such a token is a theft signal — the legitimate client
    and an attacker can't be told apart once both hold a token from the chain — so the whole family
    for that user is revoked and ``None`` is returned, forcing everyone to re-authenticate. An unknown
    token simply returns ``None`` with no side effect.

    **Atomic single-use (TOCTOU-safe):** the active→revoked flip is one conditional
    ``UPDATE … WHERE token = ? AND revoked = false``. The database serializes it, so of two concurrent
    requests presenting the same token exactly one update affects a row (``rowcount == 1``) and gets a
    fresh token; the other affects zero rows and falls through to the reuse path. Two valid successors
    are never minted from one token.
    """
    token_hash = _hash(plaintext)
    # Claim the token atomically: only the single caller that flips revoked false→true wins the race.
    claimed = await RefreshToken.where(token=token_hash, revoked=False).update({"revoked": True})
    record = await RefreshToken.where(token=token_hash).first()
    if record is None:
        return None  # never issued — nothing to rotate, no family to touch
    if getattr(claimed, "rowcount", 0) < 1:
        # Revoked nothing, but the token exists → it was already revoked: reuse (theft response).
        from arvel.auth.audit import audit

        await revoke_all_refresh_tokens(record.tokenable_id)
        audit("auth.refresh.reused", level="warning", tokenable_id=record.tokenable_id)
        return None
    new_plaintext = await issue_refresh_token(record.tokenable_id)
    return new_plaintext, record.tokenable_id


__all__ = [
    "RefreshToken",
    "issue_refresh_token",
    "revoke_all_refresh_tokens",
    "rotate_refresh_token",
]

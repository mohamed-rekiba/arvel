"""Stateless helpers for refresh-token plaintext and digest computation.

Persistence and lookup live on :class:`arvel.auth.models.RefreshToken` — the
broker calls the model directly. These helpers stay framework-public so apps
swapping in a custom broker (or running tests against the wire format) can
mint a plaintext and compute its digest without reaching into model internals.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta


def hash_refresh_token(plain: str) -> str:
    """SHA-256 hex digest of a refresh-token plaintext (64 chars)."""
    return hashlib.sha256(plain.encode()).hexdigest()


def generate_refresh_token() -> str:
    """30-byte url-safe random plaintext (40 chars after b64 encoding)."""
    return secrets.token_urlsafe(30)


def refresh_token_expires_at(ttl: timedelta) -> datetime:
    """UTC ``datetime`` ``now + ttl`` for the ``expires_at`` column."""
    return datetime.now(tz=UTC) + ttl


__all__ = [
    "generate_refresh_token",
    "hash_refresh_token",
    "refresh_token_expires_at",
]

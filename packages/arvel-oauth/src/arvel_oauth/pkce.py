"""PKCE (RFC 7636) and CSRF-state primitives.

All values come from ``secrets`` — never ``random``. The verifier uses
``token_urlsafe(96)`` for >128 bits of entropy, and the challenge is the
S256 transform only (no ``plain`` method).
"""

from __future__ import annotations

import base64
import hashlib
import secrets

# RFC 7636 §4.1: verifier is 43..128 chars. token_urlsafe(96) yields 128.
_VERIFIER_NBYTES = 96
_MIN_VERIFIER_LEN = 43


def generate_state() -> str:
    """Cryptographically random 32-byte hex CSRF state."""
    return secrets.token_hex(32)


def generate_code_verifier() -> str:
    """High-entropy, URL-safe PKCE code verifier."""
    return secrets.token_urlsafe(_VERIFIER_NBYTES)


def code_challenge_s256(verifier: str) -> str:
    """S256 challenge: base64url(sha256(verifier)), no padding."""
    if len(verifier) < _MIN_VERIFIER_LEN:
        raise ValueError("PKCE code verifier must be at least 43 characters (RFC 7636).")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


__all__ = ["code_challenge_s256", "generate_code_verifier", "generate_state"]

"""arvel.auth.two_factor — TOTP two-factor authentication on **pyotp** (mandated engine).

Parity glue only: pyotp owns the TOTP algorithm; arvel wraps secret generation, the
``otpauth://`` provisioning URI (for authenticator-app QR codes), code verification (with a
small clock-skew window), and one-time recovery codes. pyotp is imported lazily (the ``[2fa]``
extra), so ``import arvel`` stays light. Grounded in knowledge/port/15-auth-authorization.md.
"""

from __future__ import annotations

import secrets
from typing import Any


class TwoFactor:
    """TOTP helpers over pyotp (RFC 6238). The secret is stored per user; codes are 6-digit."""

    @staticmethod
    def generate_secret() -> str:
        """A fresh base32 TOTP secret to store for the user."""
        import pyotp

        return str(pyotp.random_base32())

    @staticmethod
    def provisioning_uri(secret: str, account_name: str, *, issuer: str = "arvel") -> str:
        """An ``otpauth://`` URI to render as a QR code in an authenticator app."""
        import pyotp

        totp: Any = pyotp.TOTP(secret)  # pyotp is only partially typed — funnel through Any
        return str(totp.provisioning_uri(name=account_name, issuer_name=issuer))

    @staticmethod
    def verify(secret: str, code: str, *, valid_window: int = 1) -> bool:
        """Is ``code`` valid for ``secret`` now (± ``valid_window`` 30s steps of skew)?"""
        import pyotp

        return bool(pyotp.TOTP(secret).verify(code, valid_window=valid_window))

    @staticmethod
    def current_code(secret: str) -> str:
        """The code valid at this instant (for tests / display)."""
        import pyotp

        return str(pyotp.TOTP(secret).now())

    @staticmethod
    def recovery_codes(count: int = 8) -> list[str]:
        """Single-use recovery codes to store (hashed) alongside the secret."""
        return [secrets.token_hex(5) for _ in range(count)]

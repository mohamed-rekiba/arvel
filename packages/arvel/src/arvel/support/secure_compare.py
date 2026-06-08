"""Timing-safe string comparison for attacker-controlled tokens."""

from __future__ import annotations

import hmac


def constant_time_equals(a: str, b: str) -> bool:
    """Timing-safe equality over the UTF-8 bytes of two strings.

    ``hmac.compare_digest`` raises ``TypeError`` when handed a ``str`` carrying
    non-ASCII characters. Attacker-supplied tokens — URL signatures, CSRF
    headers, maintenance bypass cookies — can hold anything, so comparing the
    encoded bytes makes a mismatch return ``False`` instead of crashing the
    guard into a 500.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


__all__ = ["constant_time_equals"]

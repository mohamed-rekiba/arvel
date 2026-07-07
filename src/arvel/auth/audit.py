"""arvel.auth.audit — one place to emit security-audit events for the auth module.

Security-relevant auth events (login failures + lockouts, refresh-token reuse, remember-me theft,
impersonation, "log out everywhere") are logged on the framework ``Log`` facade's **``security``**
channel, so they flow through the app's configured processors/sinks. Route that channel to durable,
tamper-resistant storage in production (see the security strategy).

Two invariants:

- **No secrets.** Log ids / abilities / reasons (and, for login events, the account identifier an
  operator needs to act on) — never passwords, raw tokens, or session/cookie values.
- **Best-effort, never load-bearing.** The emit is exception-guarded; a logging-backend failure (or
  no application bound, e.g. in tests) must never break or alter the auth decision. Operators alert on
  ``security``-channel downtime rather than relying on in-process raising.
"""

from __future__ import annotations

import contextlib
from typing import Any


def audit(event: str, *, level: str = "info", **fields: Any) -> None:
    """Emit a structured security-audit ``event`` (with identifier-only ``fields``) on the
    ``security`` log channel. ``level`` is ``info`` (normal) or ``warning`` (denied/abuse signal)."""
    with contextlib.suppress(Exception):
        from arvel.support.facades import Log

        getattr(Log.channel("security"), level)(event, **fields)


__all__ = ["audit"]

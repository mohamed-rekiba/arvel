"""arvel.http.session — session id rotation / invalidation (fixation defence).

``StartSession`` attaches ``request.session`` and tracks the session id on the request. These helpers
let a handler rotate or drop that id mid-request:

- ``regenerate_session(request)`` — issue a **new** session id, keeping the data. Call it right after
  a privilege change (a successful login) so a pre-login (possibly attacker-fixed) id can never be
  reused — the classic session-fixation defence.
- ``invalidate_session(request)`` — drop all session data and start a fresh empty session. Call it on
  logout.

Both flag the request so ``StartSession`` issues the new cookie (``terminate``) and forgets the old
id from the store (request teardown). Grounded in the A&A hardening backlog (G11).

Contract: these helpers add the old id to the **same** ``request._session_drop`` set that
``StartSession.handle`` holds a local reference to and drains in its ``finally`` — so mutate it in
place; never rebind ``request._session_drop`` to a new object or the drain will miss the additions.
"""

from __future__ import annotations

import secrets
from typing import Any, cast


def _new_sid() -> str:
    return secrets.token_hex(16)


def _drop_set(request: Any) -> set[str]:
    existing = getattr(request, "_session_drop", None)
    if isinstance(existing, set):
        return cast("set[str]", existing)
    drop: set[str] = set()
    request._session_drop = drop
    return drop


def regenerate_session(request: Any) -> None:
    """Rotate the session id, preserving the data (call on login — anti session-fixation)."""
    old = getattr(request, "_session_id", None)
    if old:
        _drop_set(request).add(old)
    request._session_id = _new_sid()
    request._session_set_cookie = True


def invalidate_session(request: Any) -> None:
    """Clear the session and start a fresh empty one under a new id (call on logout)."""
    old = getattr(request, "_session_id", None)
    if old:
        _drop_set(request).add(old)
    session = getattr(request, "session", None)
    if isinstance(session, dict):
        session.clear()
    request._session_id = _new_sid()
    request._session_set_cookie = True

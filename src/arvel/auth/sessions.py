"""arvel.auth.sessions — per-user session *generation*: evict other live sessions ("log out other
devices") without a per-user session registry.

A monotonic **generation** counter per user lives in the cache. Each session is *stamped* with the
user's generation at login; on every request a small middleware checks the stamp against the current
generation and, if it's behind, clears the session's auth (the device is logged out on its next
request). "Log out other devices" bumps the generation and **restamps the current session** so it
survives; "log out everywhere" bumps without restamping so every session — including the current —
falls behind. No sid enumeration, no set to keep consistent, atomic via the cache's ``increment``;
works on any cache backend. Grounded in the A&A hardening backlog (G8/L8).

Wiring (web group): add :class:`EnsureSessionCurrent` after ``StartSession``; call
:func:`stamp_session` right after a successful login; call :func:`logout_other_sessions` from your
"sign out other devices" route. ``logout_everywhere`` already bumps the generation for you.

Operational invariant: the per-user generation key must **outlive** any session that references it —
if the cache evicts it (e.g. an LRU policy) while a stamped session lingers, ``current_generation``
reads ``0`` and an evicted session could be resurrected. The keys are tiny and created only on a bump,
so keep them on a non-evicting (``noeviction``/persistent) cache or one shared with the session store.
During impersonation the generation tracks the **active** identity (``_user_id`` = the target), not
the real impersonator.
"""

from __future__ import annotations

import contextlib
from typing import Any, cast

from arvel.http.middleware import Middleware

GEN_KEY = "_session_gen"  # the generation value stamped into the session at login


def _gen_key(user_id: Any) -> str:
    return f"auth:session_gen:{user_id}"


def _resolve_cache(cache: Any) -> Any:
    """The given cache, else the container's ``cache`` binding, else ``None`` (feature inert)."""
    if cache is not None:
        return cache
    from arvel.kernel import app, has_application

    if has_application():
        with contextlib.suppress(Exception):
            return app("cache")
    return None


async def current_generation(user_id: Any, *, cache: Any = None) -> int:
    """The user's current session generation (``0`` when unset or no cache)."""
    backend = _resolve_cache(cache)
    if backend is None:
        return 0
    with contextlib.suppress(Exception):
        return int(await backend.get(_gen_key(user_id), 0) or 0)
    return 0


async def stamp_session(session: Any, user_id: Any, *, cache: Any = None) -> None:
    """Stamp ``session`` with the user's current generation — call right after a successful login."""
    if isinstance(session, dict):
        session[GEN_KEY] = await current_generation(user_id, cache=cache)


async def session_is_current(session: Any, user_id: Any, *, cache: Any = None) -> bool:
    """Whether ``session``'s stamp matches the user's current generation.

    An **un-stamped** session is treated as current (the app may not use generation tracking — don't
    lock those users out). Fails **open** (current) on a cache error, so a cache outage delays
    eviction rather than logging everyone out; pair with monitoring on the cache.
    """
    if not isinstance(session, dict):
        return True
    stamped = cast("dict[str, Any]", session).get(GEN_KEY)
    if stamped is None:
        return True
    backend = _resolve_cache(cache)
    if backend is None:
        return True  # no cache → feature inert → keep
    try:
        current = int(await backend.get(_gen_key(user_id), 0) or 0)
    except Exception:
        return True  # fail OPEN — a cache outage must not log everyone out (delay eviction instead)
    return int(stamped) == current


async def logout_other_sessions(request: Any, user_id: Any, *, cache: Any = None) -> None:
    """Invalidate the user's **other** sessions, keeping the current request's: bump the generation
    (atomic) then restamp this session so it stays current.

    Evicts other live *sessions*; it does **not** revoke their remember-me cookies, so a *remembered*
    other device re-authenticates on its next visit. To drop remembered devices too, also revoke
    remember tokens (e.g. ``logout_everywhere`` / ``clear_all_remember_tokens``).
    """
    from arvel.auth.audit import audit

    backend = _resolve_cache(cache)
    new_gen = 0
    if backend is not None:
        with contextlib.suppress(Exception):
            new_gen = int(await backend.increment(_gen_key(user_id)))
    if new_gen:
        session = getattr(request, "session", None)
        if isinstance(session, dict):
            session[GEN_KEY] = new_gen
    # Observable like the rest of the auth module; a no-op (no cache / cache error) logs a warning.
    audit(
        "auth.sessions.logout_others",
        level="info" if new_gen else "warning",
        user_id=user_id,
        ok=bool(new_gen),
    )


async def invalidate_all_sessions(user_id: Any, *, cache: Any = None) -> None:
    """Invalidate **all** the user's sessions, including the current one (password change / "log out
    everywhere"): bump the generation and don't restamp anything."""
    backend = _resolve_cache(cache)
    if backend is None:
        return
    with contextlib.suppress(Exception):
        await backend.increment(_gen_key(user_id))


class EnsureSessionCurrent(Middleware):
    """Web-group middleware (place **after** ``StartSession``, before ``AuthenticateMiddleware``):
    when the session is stamped but behind the user's current generation, clear its auth keys so an
    evicted ("logged out on another device") session becomes a guest on its next request."""

    def __init__(self, *, cache: Any = None, user_key: str = "_user_id") -> None:
        self._cache = cache
        self._user_key = user_key

    async def handle(self, request: Any, call_next: Any) -> Any:
        session = getattr(request, "session", None)
        if isinstance(session, dict):
            store = cast("dict[str, Any]", session)
            user_id = store.get(self._user_key)
            if user_id is not None and not await session_is_current(
                store, user_id, cache=self._cache
            ):
                for key in (self._user_key, GEN_KEY, "_impersonator_id"):
                    store.pop(key, None)
        return await call_next(request)

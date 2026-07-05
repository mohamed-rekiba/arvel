"""arvel.auth.confirm — password confirmation / "sudo mode".

Sensitive actions (changing email, deleting an account, rotating keys) should re-verify the password
even for an already-logged-in user. ``confirm_password`` checks the current user's password and
records a *confirmed-at* timestamp in the session; ``password_confirmed`` reports whether that
confirmation is still fresh; and ``EnsurePasswordConfirmed`` is the route-middleware that blocks
until it is. Fail closed — no/expired confirmation is denied. Grounded in the A&A hardening backlog
(G6); reads the user from ``arvel.auth.current_user`` and the session dict set by ``StartSession``.
"""

from __future__ import annotations

from typing import Any, cast

from arvel.http.middleware import Middleware

_SESSION_KEY = "_password_confirmed_at"
_SUBJECT_KEY = "_password_confirmed_for"  # identity the confirmation belongs to (anti cross-user)
DEFAULT_WINDOW = 10800  # 3 hours, matching the auth.password_timeout default


def _subject(user: Any) -> Any:
    getter = getattr(user, "get_auth_identifier", None)
    return getter() if callable(getter) else getattr(user, "id", None)


async def confirm_password(
    request: Any, password: str, *, limiter: Any = None, identifier: Any = None
) -> bool:
    """Verify the current user's ``password`` and mark the session freshly confirmed. Returns success.

    A no-op (``False``) when there's no logged-in user, no session, the password is wrong, or the
    stored hash can't be verified.

    Sudo re-auth is an online password-guessing surface, so pass an optional ``limiter`` (a
    :class:`~arvel.auth.throttle.LoginRateLimiter`) to throttle it: a locked key fails fast, each wrong
    password is counted, and a success clears the counter. The throttle key is ``identifier`` if given,
    else the current user's id. Every wrong/locked attempt is audited on the ``security`` channel.
    """
    from arvel.auth import current_user
    from arvel.auth.audit import audit
    from arvel.security import resolve_hasher

    user = current_user.get()
    session = getattr(request, "session", None)
    if user is None or not isinstance(session, dict):
        return False
    subject = identifier if identifier is not None else _subject(user)
    # never bucket distinct identifier-less users into one throttle key
    throttle = limiter if subject is not None else None
    key = str(subject)
    if throttle is not None and await throttle.too_many_attempts(key):
        audit("auth.password_confirm.locked", level="warning", identifier=key)
        return False
    stored = user.get_auth_password()
    if not (stored and password):
        return False
    try:
        valid = resolve_hasher().check(password, stored)
    except Exception:  # malformed/legacy hash → fail closed, never 500 the confirm endpoint
        return False
    if not valid:
        if throttle is not None:
            await throttle.record_failure(key)
        audit("auth.password_confirm.failed", level="warning", identifier=key)
        return False

    if throttle is not None:
        await throttle.clear(key)

    from arvel.dates import Date

    confirmed = cast("dict[str, Any]", session)
    confirmed[_SESSION_KEY] = Date.now().to_py().timestamp()
    confirmed[_SUBJECT_KEY] = _subject(user)  # bind to THIS user
    return True


def password_confirmed(request: Any, *, within: int | None = None) -> bool:
    """Whether the session holds a fresh confirmation **for the current user** (fail closed).

    Binding to the current user's identity stops a confirmation surviving a logout→login on the same
    session (cross-user sudo inheritance). ``within`` defaults to ``auth.password_timeout`` (else
    ``DEFAULT_WINDOW``) when omitted.
    """
    from arvel.auth import current_user
    from arvel.dates import Date
    from arvel.kernel.config import config_default

    window: int = (
        within if within is not None else config_default("auth.password_timeout", DEFAULT_WINDOW)
    )
    session = getattr(request, "session", None)
    if not isinstance(session, dict):
        return False
    store = cast("dict[str, Any]", session)
    confirmed_at = store.get(_SESSION_KEY)
    if confirmed_at is None:
        return False
    user = current_user.get()
    if user is None:
        return False
    subject = _subject(user)
    if subject is None or store.get(_SUBJECT_KEY) != subject:
        return False  # unidentifiable user, or the confirmation belongs to a different identity
    elapsed = float(Date.now().to_py().timestamp()) - float(confirmed_at)
    return elapsed <= window


class EnsurePasswordConfirmed(Middleware):
    """Require a fresh password confirmation (sudo) before the route runs — **403** otherwise.

    Register as an alias (e.g. ``kernel.alias({"password.confirm": EnsurePasswordConfirmed})``) and
    attach to sensitive routes. ``within=None`` (the default) resolves ``auth.password_timeout`` (else
    the 3h ``DEFAULT_WINDOW``); set the class attribute or subclass to pin a window.
    """

    within: int | None = None

    async def handle(self, request: Any, call_next: Any) -> Any:
        from arvel.http.exceptions import abort
        from arvel.localization import trans

        if not password_confirmed(request, within=self.within):
            abort(403, trans("auth.password_confirm"))
        return await call_next(request)

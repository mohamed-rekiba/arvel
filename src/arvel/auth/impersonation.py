"""arvel.auth.impersonation — admin "login as" another user, safely reversible.

An authorized user can *impersonate* another (to reproduce a bug, do support), then return to their
own identity. The impersonator's id is stashed in the session under ``_impersonator_id`` while the
active user (``_user_id`` — the same key the app's ``user_resolver`` reads, shared with remember-me)
points at the target. Starting and stopping both **regenerate the session** (it's an identity /
privilege change → fixation defence). Authorization is fail-closed: only a user whose ``impersonate``
ability allows the target may start, nesting is refused, and stopping always returns to the *real*
user. Grounded in the A&A hardening backlog (G7).
"""

from __future__ import annotations

import inspect
from typing import Any, cast

from arvel.auth.audit import audit
from arvel.http.session import regenerate_session

IMPERSONATOR_KEY = "_impersonator_id"
USER_KEY = "_user_id"  # session key the app's user_resolver reads (shared with remember-me)


def _session(request: Any) -> dict[str, Any] | None:
    session = getattr(request, "session", None)
    return cast("dict[str, Any]", session) if isinstance(session, dict) else None


def _ident(user: Any) -> Any:
    getter = getattr(user, "get_auth_identifier", None)
    return getter() if callable(getter) else getattr(user, "id", None)


def is_impersonating(request: Any) -> bool:
    """Whether the current request is running under an impersonated identity."""
    session = _session(request)
    return bool(session and session.get(IMPERSONATOR_KEY))


def impersonator_id(request: Any) -> Any:
    """The real (impersonating) user's id while impersonating, else ``None``."""
    session = _session(request)
    return session.get(IMPERSONATOR_KEY) if session else None


async def impersonate(request: Any, target: Any, *, ability: str | None = None) -> bool:
    """Begin impersonating ``target`` as the current user. Returns ``False`` (fail closed) when not
    allowed — no session, no current user, already impersonating, self-target, or the ``ability``
    check denies it (the current user must expose ``can``).

    ``ability`` defaults to ``auth.impersonation.ability`` (else ``"impersonate"``) when omitted.
    """
    from arvel.auth import current_user
    from arvel.kernel.config import config_default

    if ability is None:
        ability = config_default("auth.impersonation.ability", "impersonate")
    session = _session(request)
    impersonator = current_user.get()
    if session is None or impersonator is None or target is None:
        # every denied attempt is audited (accountability is required) — including degenerate ones.
        audit(
            "auth.impersonation.denied",
            level="warning",
            impersonator_id=_ident(impersonator) if impersonator is not None else None,
            target_id=_ident(target) if target is not None else None,
            reason="no_session" if session is None else "no_current_user_or_target",
        )
        return False
    if session.get(
        IMPERSONATOR_KEY
    ):  # already impersonating → must stop first (no nesting/escalation)
        audit(
            "auth.impersonation.denied",
            level="warning",
            impersonator_id=_ident(impersonator),
            target_id=_ident(target),
            reason="already_impersonating",
        )
        return False
    if _ident(target) == _ident(impersonator):  # no self-impersonation
        audit(
            "auth.impersonation.denied",
            level="warning",
            impersonator_id=_ident(impersonator),
            target_id=_ident(target),
            reason="self_impersonation",
        )
        return False
    can = getattr(impersonator, "can", None)  # authorize against the REAL user (fail closed)
    if not callable(can):
        audit(
            "auth.impersonation.denied",
            level="warning",
            impersonator_id=_ident(impersonator),
            target_id=_ident(target),
            reason="no_can_method",
        )
        return False
    verdict = can(ability, target)
    if inspect.isawaitable(verdict):
        verdict = await verdict
    if not verdict:
        audit(
            "auth.impersonation.denied",
            level="warning",
            impersonator_id=_ident(impersonator),
            target_id=_ident(target),
            ability=ability,
            reason="unauthorized",
        )
        return False

    session[IMPERSONATOR_KEY] = _ident(impersonator)
    session[USER_KEY] = _ident(target)
    regenerate_session(request)  # identity switch → rotate the session id
    current_user.set(
        target
    )  # effective for the rest of this request (next request resolves from session)
    audit(
        "auth.impersonation.started",
        impersonator_id=_ident(impersonator),
        target_id=_ident(target),
        ability=ability,
    )
    return True


async def stop_impersonating(request: Any) -> bool:
    """Return to the original user. Returns ``False`` when not currently impersonating."""
    from arvel.auth import current_user

    session = _session(request)
    if session is None:
        return False
    original = session.get(IMPERSONATOR_KEY)
    if not original:
        return False

    session[USER_KEY] = original
    del session[IMPERSONATOR_KEY]
    regenerate_session(request)  # identity switch back → rotate again
    current_user.set(None)  # cleared; the next request resolves the original user from the session
    audit("auth.impersonation.stopped", impersonator_id=original)
    return True


__all__ = [
    "IMPERSONATOR_KEY",
    "USER_KEY",
    "impersonate",
    "impersonator_id",
    "is_impersonating",
    "stop_impersonating",
]

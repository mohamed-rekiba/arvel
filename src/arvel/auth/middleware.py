"""arvel.auth.middleware — route-protection middleware.

The composable guards you attach to routes/groups to *enforce* auth (the
:class:`~arvel.http.middleware.AuthenticateMiddleware` only *populates* the user). Each aborts with
the right status via :func:`arvel.http.exceptions.abort` (rendered content-negotiated by the kernel:
JSON for APIs, redirect-back for web). Register the parameter-less ones as kernel aliases with
:func:`default_aliases`; ``Authorize`` is parametrised so you instantiate it per route.

These read the request's user from ``arvel.auth.current_user``, so an earlier middleware
(``AuthenticateMiddleware``) must have populated it. Grounded in the A&A hardening backlog (G1).
"""

from __future__ import annotations

from typing import Any

from arvel.http.middleware import Middleware


class Authenticate(Middleware):
    """Reject unauthenticated requests with **401**. Alias: ``auth``."""

    async def handle(self, request: Any, call_next: Any) -> Any:
        from arvel.auth import current_user
        from arvel.http.exceptions import abort

        if current_user.get() is None:
            abort(401)
        return await call_next(request)


class RequireGuest(Middleware):
    """Reject *already*-authenticated requests with **403** (e.g. on login/register). Alias: ``guest``."""

    async def handle(self, request: Any, call_next: Any) -> Any:
        from arvel.auth import current_user
        from arvel.http.exceptions import abort
        from arvel.localization import trans

        if current_user.get() is not None:
            abort(403, trans("auth.already_authenticated"))
        return await call_next(request)


class EnsureEmailVerified(Middleware):
    """Require a verified email — **401** if a guest, **403** if unverified. Alias: ``verified``.

    Treats the user as verified when its ``email_verified_at`` attribute is set (non-``None``).
    """

    async def handle(self, request: Any, call_next: Any) -> Any:
        from arvel.auth import current_user
        from arvel.http.exceptions import abort
        from arvel.localization import trans

        user = current_user.get()
        if user is None:
            abort(401)
        # Verified means a *truthy* timestamp — a falsy-but-set value ("", 0, False) is NOT verified.
        if not getattr(user, "email_verified_at", None):
            abort(403, trans("auth.unverified"))
        return await call_next(request)


def Authorize(ability: str) -> type[Middleware]:
    """Build a route-middleware **class** requiring an ability via the Gate.

    **401** if a guest, **403** if the Gate denies ``ability``. Returns a class (not an instance) so
    it drops straight into the kernel, which instantiates each route middleware:
    ``add_route(..., middleware=[Authorize("posts.update")])``. The user must be ``Authenticatable``.
    """

    class _AuthorizeAbility(Middleware):
        required_ability = ability  # introspectable for assert_abilities_defined (boot-time lint)

        async def handle(self, request: Any, call_next: Any) -> Any:
            from arvel.auth import current_user
            from arvel.http.exceptions import abort

            user = current_user.get()
            if user is None:
                abort(401)
            # Strict allow: deny on anything that isn't truthy-True (guards a custom `can`).
            if not bool(await user.can(ability)):
                abort(403)
            return await call_next(request)

    _AuthorizeAbility.__name__ = f"Authorize({ability!r})"
    _AuthorizeAbility.__qualname__ = _AuthorizeAbility.__name__
    return _AuthorizeAbility


def assert_abilities_defined(gate: Any, middlewares: Any) -> None:
    """Opt-in boot check: raise if any ``Authorize(ability)`` in ``middlewares`` names an ability the
    ``gate`` hasn't ``define``-d — turning a typo'd ability (which otherwise silently 403s every
    request, deny-by-default) into a loud failure at startup.

    ``middlewares`` is any iterable of middleware classes (e.g. the route middleware you registered).
    Only named (``Gate.define``) abilities are checked; abilities served solely by a policy method or a
    ``before`` hook should be excluded from this set or defined explicitly. Deny-by-default is
    unchanged — this only surfaces the mistake earlier.
    """
    missing = sorted(
        {
            ability
            for middleware in middlewares
            if (ability := getattr(middleware, "required_ability", None)) is not None
            and not gate.has_ability(ability)
        }
    )
    if missing:
        raise ValueError(f"Authorize() references undefined Gate abilities: {', '.join(missing)}")


def default_aliases() -> dict[str, type[Middleware]]:
    """The parameter-less route-protection middleware, ready for ``kernel.alias(...)``.

    ``{"auth": Authenticate, "guest": RequireGuest, "verified": EnsureEmailVerified}``.
    (``Authorize`` is parametrised — instantiate it per route rather than aliasing it.)
    """
    return {
        "auth": Authenticate,
        "guest": RequireGuest,
        "verified": EnsureEmailVerified,
    }

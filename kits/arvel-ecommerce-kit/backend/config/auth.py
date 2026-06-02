"""Auth configuration — JWT access tokens + opaque refresh tokens.

The framework's ``AuthServiceProvider`` reads this module via the config
loader and maps it to ``arvel.auth.config.AuthConfig``. Every key here
corresponds to a field on that Pydantic model.

``providers.users.model`` points to the kit's ``User`` model (integer PKs).
``providers.users.resource`` points to the kit's ``UserResource`` which
extends the framework base with ``theme`` and ``suspended_at`` fields the
SPA reads.
"""

from __future__ import annotations

from arvel.support.env import env

default: str = "jwt"

guards: dict[str, dict[str, object]] = {
    "jwt": {
        "driver": "jwt",
        "provider": "users",
    },
}

providers: dict[str, dict[str, object]] = {
    "users": {
        "driver": "database",
        "model": "app.models.user.User",
        "resource": "app.http.resources.auth_resources.EcommerceUserResource",
    },
}

hash: dict[str, object] = {  # noqa: A001 — framework config contract; see arvel.auth.config.AuthConfig.hash
    "driver": "argon2id",
    "memory_cost": 65536,
    "time_cost": 3,
    "parallelism": 4,
}

_secure: bool = env("REFRESH_COOKIE_SECURE", default=True)

jwt: dict[str, object] = {
    "secret": env("APP_KEY", ""),
    "algorithm": "HS256",
    "issuer": env("JWT_ISSUER", "arvel-ecommerce-kit"),
    "audience": env("JWT_AUDIENCE", "arvel-ecommerce-kit"),
    "ttl_seconds": env("JWT_TTL_SECONDS", 900),
}

refresh: dict[str, object] = {
    "ttl_seconds": env("REFRESH_TTL_SECONDS", 1_209_600),
    # Browsers enforce three rules on cookies whose name starts with ``__Host-``:
    # Secure must be set, Domain must NOT be set, and Path must equal ``/``.
    # We only emit the prefix when Secure is true so the dev / HTTP-loopback path
    # does not violate the contract.
    "cookie_name": "__Host-refresh" if _secure else "arvel_refresh",
    "cookie_secure": _secure,
    "csrf_cookie_name": "_csrf",
    "csrf_cookie_secure": _secure,
    "csrf_header": "X-CSRF-TOKEN",
}

routes: dict[str, object] = {
    # Disabled — the kit registers its own /api/auth/login that accepts
    # non-deliverable TLDs (e.g. .test) used in integration test fixtures.
    "enabled": False,
    "prefix": "/api/auth",
}

rate_limit: dict[str, object] = {
    "max_attempts": env("AUTH_RL_MAX", 5),
    "decay_seconds": env("AUTH_RL_DECAY", 60),
}

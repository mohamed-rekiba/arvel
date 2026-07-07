"""arvel.auth.jwt_guard — JWT encode/decode on **pyjwt** (mandated engine).

Parity glue only: pyjwt owns signing/verification; arvel wraps claim issuance with an
optional ``ttl`` (sets ``exp``) and a safe decode that returns ``None`` on any failure
(bad signature, expiry, tampering). pyjwt is imported lazily (the ``[jwt]`` extra), so
``import arvel`` stays light. Grounded in knowledge/port/15-auth-authorization.md.
"""

from __future__ import annotations

import time
from typing import Any


class Jwt:
    """Sign and verify JSON Web Tokens (HS256 by default) over pyjwt."""

    @staticmethod
    def encode(
        claims: dict[str, Any], secret: str, *, algorithm: str = "HS256", ttl: int | None = None
    ) -> str:
        import jwt

        payload = dict(claims)
        if ttl is not None:
            payload["exp"] = int(time.time()) + ttl
        return str(jwt.encode(payload, secret, algorithm=algorithm))

    @staticmethod
    def decode(
        token: str,
        secret: str,
        *,
        algorithms: tuple[str, ...] = ("HS256",),
        issuer: str | None = None,
        audience: str | list[str] | None = None,
        leeway: float = 0,
    ) -> dict[str, Any] | None:
        import jwt

        # exp is always required — a token with no expiry is never valid (fail closed). When an
        # issuer/audience is configured it is both enforced and required to be present.
        require = ["exp"]
        options: dict[str, Any] = {}
        if issuer is not None:
            options["issuer"] = issuer
            require.append("iss")
        if audience is not None:
            options["audience"] = audience
            require.append("aud")
        try:
            decoded: dict[str, Any] = jwt.decode(
                token,
                secret,
                algorithms=list(algorithms),
                leeway=leeway,
                options={"require": require},
                **options,
            )
        except jwt.PyJWTError:
            return None
        return decoded


__all__ = ["Jwt"]

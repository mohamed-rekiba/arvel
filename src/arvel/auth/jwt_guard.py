"""arvel.auth.jwt_guard — JWT encode/decode on **pyjwt** (mandated engine).

Parity glue only: pyjwt owns signing/verification; arvel wraps claim issuance with an
optional ``ttl`` (sets ``exp``) and a safe decode that returns ``None`` on any failure
(bad signature, expiry, tampering). pyjwt is imported lazily (the ``[jwt]`` extra), so
``import arvel`` stays light. Grounded in knowledge/port/15-auth-authorization.md.
"""

from __future__ import annotations

import time
from typing import Any


def _reject_mixed_algorithm_families(algorithms: tuple[str, ...]) -> None:
    """Refuse an ``algorithms`` list that mixes symmetric (``HS*``) and asymmetric
    (``RS*``/``PS*``/``ES*``/``EdDSA``) families. Verifying a token against both at once is the
    classic algorithm-confusion setup: an attacker takes the asymmetric *public* key (which is not
    secret) and signs a forged ``HS*`` token with it, and a verifier that also accepts ``HS*`` treats
    that public key as the HMAC secret and lets it through. Pin one family, so a token can only be
    what it was signed as."""
    algs = [a.upper() for a in algorithms]
    symmetric = any(a.startswith("HS") for a in algs)
    asymmetric = any(a.startswith(("RS", "PS", "ES", "ED")) for a in algs)
    if symmetric and asymmetric:
        raise ValueError(
            "Jwt.decode: refusing an algorithms list that mixes symmetric (HS*) and asymmetric "
            "(RS*/PS*/ES*/EdDSA) families — this enables algorithm confusion (an attacker signs an "
            "HS* token with the public key). Pin a single family, e.g. ('HS256',) or ('RS256',)."
        )


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

        # A misconfigured algorithms list is a developer error, not a bad token — raise, don't
        # return None, so it surfaces loudly instead of silently weakening verification.
        _reject_mixed_algorithm_families(algorithms)

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

"""arvel.auth.oidc — the OIDC / Keycloak guard driver.

Validates an OIDC bearer JWT (signature against the IdP JWKS, plus issuer / audience / expiry) and
produces a ``Principal`` whose ``subject`` is the ``sub`` claim and whose ``claims`` carry
``email`` / ``email_verified`` / ``groups`` (or ``realm_access.roles``) for the identity and authz
layers downstream.

The token **verifier is injectable** — the driver never decodes a token without validating it, and
the default verifier (pyjwt + the IdP JWKS, the ``[jwt]`` extra) is imported lazily so this module
stays import-light (NFR G2) and so tests can inject a fake verifier with no network. Grounded in
DR-0009 / DR-0010 and projects/arvel/architecture/auth-rearchitecture.md.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.auth.identity import Principal

# token -> verified claims, or None when verification fails. NEVER returns unverified claims.
ClaimsVerifier = Callable[[str], Awaitable[Mapping[str, Any] | None]]


def _bearer_token(request: Any) -> str | None:
    """The ``Authorization: Bearer <jwt>`` token, or ``None``."""
    header = request.header("authorization") if hasattr(request, "header") else None
    if not header or not header.lower().startswith("bearer "):
        return None
    return str(header[7:].strip()) or None


class OidcGuard:
    """Authenticate a request from a validated OIDC bearer JWT.

    ``verifier`` validates the token and returns its claims (or ``None``). The default
    ``GuardManager`` wires it to a JWKS verifier built from ``auth.oidc`` config; tests inject a
    fake. ``subject_claim`` is the stable subject (``sub``); it is never the email.
    """

    def __init__(
        self,
        verifier: ClaimsVerifier,
        *,
        provider: str = "oidc",
        subject_claim: str = "sub",
    ) -> None:
        self._verify_token = verifier
        self._provider = provider
        self._subject_claim = subject_claim

    async def verify(self, request: Any) -> Principal | None:
        token = _bearer_token(request)
        if token is None:
            return None
        claims = await self._verify_token(token)
        if claims is None:
            return None
        subject = claims.get(self._subject_claim)
        if not subject:
            return None
        from arvel.auth.identity import Principal

        return Principal(provider=self._provider, subject=str(subject), claims=dict(claims))


def jwks_verifier(
    *,
    jwks_uri: str,
    issuer: str,
    audience: str,
    algorithms: tuple[str, ...] = ("RS256",),
    leeway: float = 30,
) -> ClaimsVerifier:
    """A ``ClaimsVerifier`` that validates a token against the IdP JWKS (RS256) via pyjwt.

    Verifies signature, ``iss``, ``aud``, and **requires** ``exp``/``iss``/``aud``/``sub`` (so a
    token missing ``exp`` is rejected, not treated as non-expiring), with a small clock ``leeway``.
    pyjwt and its JWKS client are imported lazily (the ``[jwt]`` extra) so importing this module
    never pulls them into the light core, and the ``PyJWKClient`` is constructed **once** (it caches
    keys with a TTL) rather than per request.
    """
    import jwt
    from jwt import PyJWKClient

    client = PyJWKClient(jwks_uri)  # built once; caches signing keys (no per-request fetch)

    async def _verify(token: str) -> Mapping[str, Any] | None:
        from anyio.to_thread import run_sync

        try:
            # JWKS fetch is a blocking network call on a cache miss — keep it off the event loop
            signing_key = await run_sync(client.get_signing_key_from_jwt, token)
            decoded: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(algorithms),
                issuer=issuer,
                audience=audience,
                leeway=leeway,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError:
            return None
        return decoded

    return _verify

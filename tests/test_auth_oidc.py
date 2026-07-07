"""OIDC/Keycloak guard driver, with an injected verifier (no network)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from arvel.auth.oidc import OidcGuard, jwks_verifier


class _Req:
    def __init__(self, authorization: str | None) -> None:
        self._authorization = authorization

    def header(self, name: str) -> str | None:
        return self._authorization if name.lower() == "authorization" else None


async def _good_verifier(token: str) -> Mapping[str, Any] | None:
    if token == "valid":
        return {
            "sub": "kc-abc",
            "email": "ada@corp.com",
            "email_verified": True,
            "groups": ["/eng/backend"],
        }
    return None


@pytest.mark.asyncio
async def test_valid_token_yields_principal_with_claims() -> None:
    guard = OidcGuard(_good_verifier, provider="keycloak")
    principal = await guard.verify(_Req("Bearer valid"))
    assert principal is not None
    assert principal.provider == "keycloak"
    assert principal.subject == "kc-abc"  # the sub claim, not the email
    assert principal.email == "ada@corp.com"
    assert principal.email_verified is True
    assert principal.claims["groups"] == ["/eng/backend"]


@pytest.mark.asyncio
async def test_invalid_token_returns_none() -> None:
    guard = OidcGuard(_good_verifier)
    assert await guard.verify(_Req("Bearer nope")) is None


@pytest.mark.asyncio
async def test_missing_or_malformed_header_returns_none() -> None:
    guard = OidcGuard(_good_verifier)
    assert await guard.verify(_Req(None)) is None
    assert await guard.verify(_Req("Basic xyz")) is None
    assert await guard.verify(_Req("Bearer ")) is None


@pytest.mark.asyncio
async def test_token_without_subject_is_rejected() -> None:
    async def no_sub(_token: str) -> Mapping[str, Any]:
        return {"email": "ada@corp.com", "email_verified": True}  # no `sub`

    guard = OidcGuard(no_sub)
    assert await guard.verify(_Req("Bearer valid")) is None


@pytest.mark.asyncio
async def test_jwks_verifier_rejects_garbage_without_raising() -> None:
    # A bogus token must not raise — the verifier swallows PyJWTError and returns None.
    verifier = jwks_verifier(
        jwks_uri="https://idp.test/jwks", issuer="https://idp.test", audience="arvel"
    )
    assert await verifier("not-a-jwt") is None


@pytest.mark.asyncio
async def test_string_email_verified_is_normalized() -> None:
    # defense-in-depth: an IdP string "false" must not coerce to True
    async def verifier(_t: str) -> dict[str, Any]:
        return {"sub": "kc-1", "email": "ada@corp.com", "email_verified": "false"}

    principal = await OidcGuard(verifier).verify(_Req("Bearer valid"))
    assert principal is not None
    assert principal.email_verified is False


def test_create_oidc_driver_fails_loud_on_missing_config() -> None:
    # misconfigured auth.oidc must raise, not silently reject every token
    from arvel.auth.guards import GuardManager

    class _App:
        def config(self, key: str, default: Any = None) -> Any:
            return {"issuer": "https://idp.test"}  # missing jwks_uri + audience

    with pytest.raises(ValueError, match="jwks_uri"):
        GuardManager(_App()).guard("oidc")


def test_create_oidc_driver_with_no_app_treats_config_as_missing() -> None:
    from arvel.auth.guards import GuardManager

    with pytest.raises(ValueError, match="jwks_uri"):
        GuardManager().guard("oidc")  # no app bound at all: skips the config lookup entirely


def test_create_oidc_driver_treats_a_non_dict_config_as_missing() -> None:
    from arvel.auth.guards import GuardManager

    class _App:
        def config(self, key: str, default: Any = None) -> Any:
            return None  # no auth.oidc section configured at all

    with pytest.raises(ValueError, match="jwks_uri"):
        GuardManager(_App()).guard("oidc")


def test_create_oidc_driver_builds_a_working_guard_from_full_config() -> None:
    from arvel.auth.guards import GuardManager

    class _App:
        def config(self, key: str, default: Any = None) -> Any:
            return {
                "jwks_uri": "https://idp.test/jwks",
                "issuer": "https://idp.test",
                "audience": "arvel",
                "provider": "keycloak",
            }

    guard = GuardManager(_App()).guard("oidc")
    assert isinstance(guard, OidcGuard)
    assert guard._provider == "keycloak"

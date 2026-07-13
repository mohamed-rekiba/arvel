"""Auth (doc 15) — JWT on pyjwt (mandated engine). Test-first."""

from __future__ import annotations

import pytest

from arvel.auth.jwt_guard import Jwt

SIG = "unit-test-signing-value-padded-past-32-bytes"


def test_encode_decode_roundtrip() -> None:
    token = Jwt.encode({"sub": "42", "role": "admin"}, SIG, ttl=3600)
    claims = Jwt.decode(token, SIG)
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["role"] == "admin"


def test_token_without_exp_is_rejected() -> None:
    # a non-expiring token must never validate — fail closed
    token = Jwt.encode({"sub": "1"}, SIG)  # no ttl -> no exp
    assert Jwt.decode(token, SIG) is None


def test_issuer_is_enforced_when_configured() -> None:
    token = Jwt.encode({"sub": "1", "iss": "trusted"}, SIG, ttl=3600)
    assert Jwt.decode(token, SIG, issuer="trusted") is not None
    assert Jwt.decode(token, SIG, issuer="someone-else") is None
    # a token missing iss is rejected once an issuer is required
    bare = Jwt.encode({"sub": "1"}, SIG, ttl=3600)
    assert Jwt.decode(bare, SIG, issuer="trusted") is None


def test_audience_is_enforced_when_configured() -> None:
    token = Jwt.encode({"sub": "1", "aud": "api"}, SIG, ttl=3600)
    assert Jwt.decode(token, SIG, audience="api") is not None
    assert Jwt.decode(token, SIG, audience="other") is None


def test_wrong_secret_returns_none() -> None:
    token = Jwt.encode({"sub": "1"}, SIG)
    assert Jwt.decode(token, "a-totally-different-secret-of-ample-length") is None


def test_expired_token_returns_none() -> None:
    token = Jwt.encode({"sub": "1"}, SIG, ttl=-1)  # exp in the past
    assert Jwt.decode(token, SIG) is None


def test_tampered_token_returns_none() -> None:
    assert Jwt.decode("not.a.valid-token", SIG) is None


def test_mixing_symmetric_and_asymmetric_algorithms_is_refused() -> None:
    # algorithm-confusion guard: accepting HS* AND RS* at once lets an attacker sign an HS* token
    # with the (public) RS key. Refuse the mix loudly — a config error, not a bad token.
    token = Jwt.encode({"sub": "1"}, SIG, ttl=3600)
    with pytest.raises(ValueError, match="algorithm confusion"):
        Jwt.decode(token, SIG, algorithms=("RS256", "HS256"))


def test_single_family_lists_are_untouched() -> None:
    # a pinned symmetric list still verifies its own token
    token = Jwt.encode({"sub": "1"}, SIG, ttl=3600)
    assert Jwt.decode(token, SIG, algorithms=("HS256",)) is not None
    # a pinned asymmetric-only list is allowed through the guard (fails later on the HS token's
    # signature -> None), proving the guard blocks *mixing*, not asymmetric verification itself
    assert Jwt.decode(token, SIG, algorithms=("RS256", "ES256")) is None

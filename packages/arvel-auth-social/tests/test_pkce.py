"""PKCE primitives — entropy, length, and S256 transform (RFC 7636)."""

from __future__ import annotations

import base64
import hashlib

import pytest
from arvel_auth_social.pkce import code_challenge_s256, generate_code_verifier, generate_state


def test_state_is_unique_and_long() -> None:
    a, b = generate_state(), generate_state()
    assert a != b
    assert len(a) == 64  # 32 bytes hex


def test_verifier_meets_rfc_minimum_length() -> None:
    verifier = generate_code_verifier()
    assert len(verifier) >= 43


def test_s256_challenge_matches_manual_transform() -> None:
    verifier = generate_code_verifier()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert code_challenge_s256(verifier) == expected
    assert "=" not in code_challenge_s256(verifier)


def test_short_verifier_rejected() -> None:
    with pytest.raises(ValueError, match="at least 43"):
        code_challenge_s256("too-short")

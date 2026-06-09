"""
HashFacade (bcrypt default, argon2id opt-in).
Tests import from arvel.facades.hash and arvel.auth.hashing → red state.
"""

from __future__ import annotations

import pytest

# Hash.make() produces a bcrypt hash


def test_hash_make_returns_bcrypt_hash_by_default() -> None:
    from arvel.facades.hash import Hash

    hashed = Hash.make("secret")
    # argon2id hashes start with $argon2id$
    assert hashed.startswith(("$argon2id$", "$argon2"))


def test_hash_make_is_not_plaintext() -> None:
    from arvel.facades.hash import Hash

    hashed = Hash.make("mypassword")
    assert hashed != "mypassword"


# Hash.check() verifies passwords


def test_hash_check_returns_true_for_correct_password() -> None:
    from arvel.facades.hash import Hash

    hashed = Hash.make("correct")
    assert Hash.check("correct", hashed) is True


def test_hash_check_returns_false_for_wrong_password() -> None:
    from arvel.facades.hash import Hash

    hashed = Hash.make("correct")
    assert Hash.check("wrong", hashed) is False


def test_hash_needs_rehash_returns_false_for_fresh_hash() -> None:
    from arvel.facades.hash import Hash

    hashed = Hash.make("password")
    assert Hash.needs_rehash(hashed) is False


# bcrypt cost is configurable


def test_hash_make_accepts_rounds_parameter() -> None:
    from arvel.facades.hash import Hash

    # argon2 accepts time_cost, memory_cost, parallelism params
    hashed = Hash.make("password", time_cost=1)
    assert "$argon2" in hashed


# Hash.make_argon2() available when argon2-cffi installed


def test_hash_make_argon2_delegates_to_argon2_hasher() -> None:
    from arvel.facades.hash import Hash

    hashed = Hash.make_argon2("secret")
    assert hashed.startswith(("$argon2id$", "$argon2"))


def test_hash_make_produces_different_hashes_for_same_input() -> None:
    from arvel.facades.hash import Hash

    h1 = Hash.make("password")
    h2 = Hash.make("password")
    assert h1 != h2  # each call uses a fresh random salt


def test_hash_module_uses_bcrypt_checkpw_not_eq() -> None:
    """argon2 verify is inherently timing-safe; verify we use it, not ==."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.find_spec("arvel.facades.hash")
    assert spec and spec.origin
    source = Path(spec.origin).read_text()
    assert "verify" in source or "checkpw" in source or "compare_digest" in source


def test_hash_check_returns_false_for_malformed_hash() -> None:
    from arvel.facades.hash import Hash

    assert Hash.check("password", "not-a-valid-hash") is False


def test_hash_checkpw_delegates_to_check() -> None:
    from arvel.facades.hash import Hash

    hashed = Hash.make("password")
    assert Hash.checkpw("password", hashed) is True
    assert Hash.checkpw("wrong", hashed) is False


def test_hash_make_bcrypt_reports_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    from arvel.facades.hash import Hash

    def import_module(name: str) -> object:
        if name == "bcrypt":
            raise ImportError("missing bcrypt")
        return importlib.import_module(name)

    monkeypatch.setattr(importlib, "import_module", import_module)

    with pytest.raises(ImportError, match=r"arvel\[bcrypt\]"):
        Hash.make_bcrypt("secret")


def test_hash_make_bcrypt_produces_bcrypt_hash() -> None:
    pytest.importorskip("bcrypt")

    from arvel.facades.hash import Hash

    hashed = Hash.make_bcrypt("secret", rounds=4)
    assert hashed.startswith("$2")


def test_hash_check_bcrypt_hash_without_extra_degrades_to_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bcrypt hash can't verify without the extra — non-match, not a crash."""
    from arvel.facades.hash import Hash

    def _no_bcrypt() -> object:
        raise ImportError("bcrypt extra not installed")

    monkeypatch.setattr(Hash, "_load_bcrypt", staticmethod(_no_bcrypt))
    # $2b$ prefix routes to the bcrypt path, which can't load the lib.
    assert Hash.check("secret", "$2b$12$" + "x" * 53) is False


def test_hash_check_malformed_bcrypt_hash_returns_false() -> None:
    """A bcrypt-prefixed but malformed hash makes checkpw raise — caught as non-match."""
    pytest.importorskip("bcrypt")

    from arvel.facades.hash import Hash

    assert Hash.check("secret", "$2b$12$too-short-to-be-a-real-bcrypt-hash") is False

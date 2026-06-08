"""WI-arvel-016 — Hash.check / needs_rehash must be algorithm-aware.

A bcrypt hash (from Hash.make_bcrypt, or imported from a Laravel users table)
must verify through Hash.check and not crash Hash.needs_rehash.
"""

from __future__ import annotations

import pytest
from arvel.facades.hash import Hash


def test_check_verifies_bcrypt_hash() -> None:
    pytest.importorskip("bcrypt")
    hashed = Hash.make_bcrypt("secret", rounds=4)
    assert Hash.check("secret", hashed) is True
    assert Hash.check("wrong", hashed) is False


def test_checkpw_verifies_bcrypt_hash() -> None:
    pytest.importorskip("bcrypt")
    hashed = Hash.make_bcrypt("secret", rounds=4)
    assert Hash.checkpw("secret", hashed) is True
    assert Hash.checkpw("wrong", hashed) is False


def test_check_still_verifies_argon2_hash() -> None:
    hashed = Hash.make("secret")
    assert Hash.check("secret", hashed) is True
    assert Hash.check("wrong", hashed) is False


def test_check_verifies_laravel_style_2y_hash() -> None:
    """Laravel writes $2y$ bcrypt hashes; the importer path must verify them."""
    pytest.importorskip("bcrypt")
    # bcrypt for "secret" at cost 4, normalized to the $2y$ identifier Laravel uses.
    hashed = Hash.make_bcrypt("secret", rounds=4).replace("$2b$", "$2y$", 1)
    assert Hash.check("secret", hashed) is True


def test_check_returns_false_for_empty_hash() -> None:
    assert Hash.check("anything", "") is False


def test_needs_rehash_flags_bcrypt_for_argon2_upgrade() -> None:
    pytest.importorskip("bcrypt")
    # Default algorithm is argon2id, so any bcrypt hash should want an upgrade.
    assert Hash.needs_rehash(Hash.make_bcrypt("secret")) is True
    assert Hash.needs_rehash(Hash.make_bcrypt("secret", rounds=4)) is True


def test_needs_rehash_false_for_fresh_argon2() -> None:
    assert Hash.needs_rehash(Hash.make("secret")) is False

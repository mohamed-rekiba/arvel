"""Tests for password hashing — bcrypt and argon2 drivers."""

from __future__ import annotations

from importlib.util import find_spec

import pytest

from arvel.security.hashing import Argon2Hasher, BcryptHasher, HashManager

_skip_argon2 = pytest.mark.skipif(find_spec("argon2") is None, reason="argon2-cffi not installed")


class TestBcryptHasher:
    def test_make_returns_bcrypt_hash(self) -> None:
        hasher = BcryptHasher(rounds=4)
        hashed = hasher.make("secret123")
        assert hashed.startswith("$2")

    def test_check_correct_password(self) -> None:
        hasher = BcryptHasher(rounds=4)
        hashed = hasher.make("secret123")
        assert hasher.check("secret123", hashed) is True

    def test_check_wrong_password(self) -> None:
        hasher = BcryptHasher(rounds=4)
        hashed = hasher.make("secret123")
        assert hasher.check("wrong", hashed) is False

    def test_needs_rehash_different_rounds(self) -> None:
        hasher_4 = BcryptHasher(rounds=4)
        hashed = hasher_4.make("secret123")
        hasher_12 = BcryptHasher(rounds=12)
        assert hasher_12.needs_rehash(hashed) is True

    def test_needs_rehash_same_rounds(self) -> None:
        hasher = BcryptHasher(rounds=4)
        hashed = hasher.make("secret123")
        assert hasher.needs_rehash(hashed) is False

    def test_needs_rehash_non_bcrypt_hash(self) -> None:
        hasher = BcryptHasher()
        assert hasher.needs_rehash("not-a-bcrypt-hash") is True

    def test_password_too_long_raises(self) -> None:
        hasher = BcryptHasher(rounds=4)
        with pytest.raises(Exception, match="72-byte"):
            hasher.make("a" * 73)


@_skip_argon2
class TestArgon2Hasher:
    def test_make_returns_argon2_hash(self) -> None:
        hasher = Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1)
        hashed = hasher.make("secret123")
        assert "$argon2" in hashed

    def test_check_correct_password(self) -> None:
        hasher = Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1)
        hashed = hasher.make("secret123")
        assert hasher.check("secret123", hashed) is True

    def test_check_wrong_password(self) -> None:
        hasher = Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1)
        hashed = hasher.make("secret123")
        assert hasher.check("wrong", hashed) is False

    def test_needs_rehash_different_params(self) -> None:
        h1 = Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1)
        hashed = h1.make("secret123")
        h2 = Argon2Hasher(time_cost=3, memory_cost=65536, parallelism=4)
        assert h2.needs_rehash(hashed) is True


class TestHashManager:
    def test_bcrypt_driver(self) -> None:
        manager = HashManager(driver="bcrypt", rounds=4)
        hashed = manager.make("password")
        assert manager.check("password", hashed)
        assert manager.driver == "bcrypt"

    @_skip_argon2
    def test_argon2_driver(self) -> None:
        manager = HashManager(driver="argon2", time_cost=1, memory_cost=1024, parallelism=1)
        hashed = manager.make("password")
        assert manager.check("password", hashed)
        assert manager.driver == "argon2"

    def test_unknown_driver_raises(self) -> None:
        with pytest.raises(Exception, match="Unknown hashing driver"):
            HashManager(driver="md5")

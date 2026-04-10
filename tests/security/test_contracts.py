"""Tests for security contracts — HasherContract and EncrypterContract ABCs."""

from __future__ import annotations

import pytest

from arvel.security.contracts import EncrypterContract, HasherContract


class TestHasherContract:
    def test_is_abstract(self) -> None:
        abstract_cls: type = HasherContract
        with pytest.raises(TypeError):
            abstract_cls()

    def test_subclass_must_implement_make(self) -> None:
        class PartialHasher(HasherContract):
            def check(self, password: str, hashed: str) -> bool:
                return True

            def needs_rehash(self, hashed: str) -> bool:
                return False

        partial_cls: type = PartialHasher
        with pytest.raises(TypeError):
            partial_cls()

    def test_concrete_implementation(self) -> None:
        class FakeHasher(HasherContract):
            def make(self, password: str) -> str:
                return f"hashed_{password}"

            def check(self, password: str, hashed: str) -> bool:
                return hashed == f"hashed_{password}"

            def needs_rehash(self, hashed: str) -> bool:
                return False

        hasher = FakeHasher()
        assert hasher.make("secret") == "hashed_secret"
        assert hasher.check("secret", "hashed_secret") is True
        assert hasher.needs_rehash("hashed_secret") is False


class TestEncrypterContract:
    def test_is_abstract(self) -> None:
        abstract_cls: type = EncrypterContract
        with pytest.raises(TypeError):
            abstract_cls()

    def test_concrete_implementation(self) -> None:
        class FakeEncrypter(EncrypterContract):
            def encrypt(self, value: str) -> str:
                return f"enc_{value}"

            def decrypt(self, payload: str) -> str:
                return payload.removeprefix("enc_")

        enc = FakeEncrypter()
        encrypted = enc.encrypt("hello")
        assert encrypted == "enc_hello"
        assert enc.decrypt(encrypted) == "hello"

"""WI-arvel-018 — Epic 006 Story 3: declarative encrypted casts.

``__casts__`` gains ``"encrypted"`` (and ``encrypted:json|array|object|collection``).
Writes encrypt through the ``Crypt`` facade; reads decrypt. The stored column value
is ciphertext; the attribute and ``to_dict()`` expose the decrypted value, matching
Eloquent's ``toArray``.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
from arvel.database import Model
from arvel.database.exceptions import DecryptionError
from arvel.encryption import Encrypter
from arvel.facades.crypt import Crypt
from arvel.support.collections import Collection
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

_KEY = bytes(range(32))


@pytest.fixture(autouse=True)
def pinned_encrypter() -> Iterator[None]:
    Crypt.set_encrypter(Encrypter(_KEY))
    yield
    Crypt.set_encrypter(None)


class _Secret(Model):
    __tablename__ = "wi018_secrets"
    __casts__: ClassVar[dict[str, str]] = {
        "ssn": "encrypted",
        "prefs": "encrypted:array",
        "profile": "encrypted:object",
        "tags": "encrypted:collection",
    }
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    ssn: Mapped[Any] = mapped_column(String(512), default=None)
    prefs: Mapped[Any] = mapped_column(String(512), default=None)
    profile: Mapped[Any] = mapped_column(String(512), default=None)
    tags: Mapped[Any] = mapped_column(String(512), default=None)


def _raw(instance: Any, name: str) -> Any:
    return object.__getattribute__(instance, name)


class TestEncrypterRoundTrip:
    def test_string_round_trip(self) -> None:
        enc = Encrypter(_KEY)
        token = enc.encrypt_string("hello")
        assert token != "hello"
        assert enc.decrypt_string(token) == "hello"

    def test_value_round_trip(self) -> None:
        enc = Encrypter(_KEY)
        token = enc.encrypt({"a": 1, "b": [2, 3]})
        assert enc.decrypt(token) == {"a": 1, "b": [2, 3]}

    def test_non_deterministic(self) -> None:
        enc = Encrypter(_KEY)
        assert enc.encrypt_string("x") != enc.encrypt_string("x")

    def test_wrong_key_raises(self) -> None:
        token = Encrypter(_KEY).encrypt_string("secret")
        with pytest.raises(DecryptionError):
            Encrypter(bytes(range(1, 33))).decrypt_string(token)

    def test_rejects_short_key(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            Encrypter(b"short")


class TestEncryptedStringCast:
    def test_stored_value_is_ciphertext(self) -> None:
        s = _Secret(ssn="123-45-6789")
        assert _raw(s, "ssn") != "123-45-6789"
        assert isinstance(_raw(s, "ssn"), str)

    def test_read_decrypts(self) -> None:
        s = _Secret(ssn="123-45-6789")
        assert s.ssn == "123-45-6789"

    def test_to_dict_exposes_plaintext(self) -> None:
        s = _Secret(ssn="123-45-6789")
        assert s.to_dict()["ssn"] == "123-45-6789"

    def test_loaded_ciphertext_decrypts_on_read(self) -> None:
        token = Crypt.encrypt_string("from-db")
        s = _Secret()
        object.__setattr__(s, "ssn", token)
        assert s.ssn == "from-db"


class TestEncryptedArrayCast:
    def test_round_trip(self) -> None:
        s = _Secret(prefs=["dark", "compact"])
        assert _raw(s, "prefs") != ["dark", "compact"]
        assert s.prefs == ["dark", "compact"]

    def test_to_dict_emits_list(self) -> None:
        s = _Secret(prefs=[1, 2, 3])
        assert s.to_dict()["prefs"] == [1, 2, 3]


class TestEncryptedObjectCast:
    def test_read_returns_namespace(self) -> None:
        s = _Secret(profile={"name": "kira", "age": 30})
        assert isinstance(s.profile, SimpleNamespace)
        assert s.profile.name == "kira"

    def test_to_dict_emits_dict(self) -> None:
        s = _Secret(profile={"name": "kira"})
        assert s.to_dict()["profile"] == {"name": "kira"}


class TestEncryptedCollectionCast:
    def test_read_returns_collection(self) -> None:
        s = _Secret(tags=["a", "b"])
        tags = cast("Collection[str]", s.tags)
        assert isinstance(tags, Collection)
        assert list(tags) == ["a", "b"]

    def test_to_dict_emits_list(self) -> None:
        s = _Secret(tags=["x", "y"])
        assert s.to_dict()["tags"] == ["x", "y"]


def _define_bad_model() -> type[Model]:
    class Bad(Model):
        __tablename__ = "wi018_bad"
        __casts__: ClassVar[dict[str, str]] = {"x": "encrypted:bogus"}
        id: Mapped[int] = mapped_column(
            Integer, primary_key=True, autoincrement=True, init=False, default=None
        )
        x: Mapped[Any] = mapped_column(String(80), default=None)

    return Bad


class TestInvalidVariant:
    def test_unknown_variant_raises_at_definition(self) -> None:
        with pytest.raises(ValueError, match="not a recognised encrypted cast"):
            _define_bad_model()

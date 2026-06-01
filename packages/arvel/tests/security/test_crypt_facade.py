"""Crypt facade refuses to encrypt until APP_KEY (or an explicit override) is set."""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator

import pytest
from arvel.encryption.encrypter import Encrypter, MissingAppKeyError
from arvel.facades.crypt import Crypt


def _fresh_app_key() -> str:
    # A unique key per test guarantees a cache miss without touching Crypt's
    # private cache, so the build-then-cache path runs from a clean slate.
    return "base64:" + base64.b64encode(os.urandom(32)).decode("ascii")


@pytest.fixture
def no_app_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("APP_KEY", raising=False)
    Crypt.set_encrypter(None)
    try:
        yield
    finally:
        Crypt.set_encrypter(None)


@pytest.fixture
def with_app_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    key = _fresh_app_key()
    monkeypatch.setenv("APP_KEY", key)
    Crypt.set_encrypter(None)
    try:
        yield key
    finally:
        Crypt.set_encrypter(None)


def test_encrypter_without_app_key_raises(no_app_key: None) -> None:
    with pytest.raises(MissingAppKeyError, match="APP_KEY is not set"):
        Crypt.encrypter()


def test_encrypter_builds_and_caches_per_key(with_app_key: str) -> None:
    first = Crypt.encrypter()
    assert isinstance(first, Encrypter)
    # Second call for the same APP_KEY is served from the cache.
    assert Crypt.encrypter() is first


def test_override_takes_precedence_over_app_key(with_app_key: str) -> None:
    override = Encrypter.from_app_key(with_app_key)
    Crypt.set_encrypter(override)
    assert Crypt.encrypter() is override

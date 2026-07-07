"""Rotating APP_KEY must not break existing ciphertext: the provider wires
config('app.previous_keys') into the Encrypter's fallback ring."""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest

from arvel.kernel.application import Application
from arvel.kernel.globals import set_application
from arvel.security import DecryptionFailed, Encrypter
from arvel.security.provider import SecurityServiceProvider


@pytest.fixture
def fresh_app() -> Iterator[Application]:
    app = Application()
    set_application(app)
    yield app
    set_application(None)


def _configure(app: Application, values: dict[str, object]) -> None:
    for key, value in values.items():
        app.config().set(key, value)


def _encrypter(app: Application) -> Encrypter:
    SecurityServiceProvider(app).register()
    return app.make("encrypter")


OLD_KEY = "base64:" + base64.b64encode(b"o" * 32).decode()
NEW_KEY = "base64:" + base64.b64encode(b"n" * 32).decode()


def test_rotated_key_still_decrypts_old_ciphertext(fresh_app: Application) -> None:
    _configure(fresh_app, {"app.key": OLD_KEY})
    token = _encrypter(fresh_app).encrypt({"user": 1})

    rotated = Application()
    set_application(rotated)
    _configure(rotated, {"app.key": NEW_KEY, "app.previous_keys": OLD_KEY})
    enc = _encrypter(rotated)
    assert enc.decrypt(token) == {"user": 1}
    # new writes use the current key: decryptable without the ring
    fresh_token = enc.encrypt("x")
    assert Encrypter(NEW_KEY).decrypt(fresh_token) == "x"


def test_previous_keys_accepts_comma_separated_string(fresh_app: Application) -> None:
    _configure(fresh_app, {"app.key": OLD_KEY})
    token = _encrypter(fresh_app).encrypt("payload")

    rotated = Application()
    set_application(rotated)
    _configure(
        rotated,
        {
            "app.key": NEW_KEY,
            "app.previous_keys": f" {OLD_KEY} , {'base64:' + base64.b64encode(b'z' * 32).decode()}",
        },
    )
    assert _encrypter(rotated).decrypt(token) == "payload"


def test_empty_ring_means_rotation_breaks_old_tokens(fresh_app: Application) -> None:
    _configure(fresh_app, {"app.key": OLD_KEY})
    token = _encrypter(fresh_app).encrypt("payload")

    rotated = Application()
    set_application(rotated)
    _configure(rotated, {"app.key": NEW_KEY})
    with pytest.raises(DecryptionFailed):
        _encrypter(rotated).decrypt(token)

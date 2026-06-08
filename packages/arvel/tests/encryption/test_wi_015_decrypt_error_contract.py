"""WI-015 — Encrypter.decrypt_string raises DecryptionError for any bad payload.

The app `Encrypter` documents `DecryptionError` as its failure type, and its
sibling column type (`database.casts.EncryptedType`) already funnels every
malformed input into `DecryptionError`. Laravel's `Encrypter::decrypt` likewise
raises `DecryptException` for every invalid payload. `decrypt_string` used to let
a non-base64 payload escape as a raw `binascii.Error`, so callers catching the
documented `DecryptionError` (e.g. the `Crypt` facade decrypting an
attacker-controlled token) got an uncaught error instead.
"""

from __future__ import annotations

import base64
import os

import pytest
from arvel.database.exceptions import DecryptionError
from arvel.encryption import Encrypter


def _encrypter() -> Encrypter:
    return Encrypter(os.urandom(32))


def test_round_trip_string() -> None:
    enc = _encrypter()
    assert enc.decrypt_string(enc.encrypt_string("hello")) == "hello"


def test_round_trip_value() -> None:
    enc = _encrypter()
    payload: dict[str, object] = {"a": 1, "b": ["x", "y"]}
    assert enc.decrypt(enc.encrypt(payload)) == payload


@pytest.mark.parametrize(
    "bad",
    [
        "!!!not-base64!!!",  # invalid base64 alphabet
        "a",  # invalid base64 length
        "",  # empty
        "@@@@",  # decodes, wrong version byte
    ],
)
def test_malformed_payload_raises_decryption_error(bad: str) -> None:
    """No raw binascii.Error / IndexError — always the documented type."""
    with pytest.raises(DecryptionError):
        _encrypter().decrypt_string(bad)


def test_wrong_key_raises_decryption_error() -> None:
    token = _encrypter().encrypt_string("secret")
    with pytest.raises(DecryptionError):
        _encrypter().decrypt_string(token)


def test_tampered_ciphertext_raises_decryption_error() -> None:
    enc = _encrypter()
    raw = bytearray(base64.b64decode(enc.encrypt_string("secret")))
    raw[-1] ^= 0x01  # flip a tag bit
    with pytest.raises(DecryptionError):
        enc.decrypt_string(base64.b64encode(bytes(raw)).decode("ascii"))

"""Security-review hardening for EncryptedType wire format (Stage 4b).

Covers:

- Versioned wire format: the on-disk ciphertext starts with the format
  version byte so future formats can coexist.
- Key-id binding: a column written under one key-id won't decrypt under
  another key-id, even if the bytes happen to be the same key.
- AAD binding: ciphertext written for column A with associated_data
  ``b"posts.body"`` won't decrypt under a different AAD.
"""

from __future__ import annotations

import base64
import os

import pytest
from arvel.database import EncryptedType
from arvel.database.exceptions import DecryptionError
from sqlalchemy.dialects import sqlite

KEY = b"k" * 32
# A real Dialect instance for type-correct calls into TypeDecorator hooks.
# EncryptedType doesn't read the dialect, but SQLAlchemy's signature requires
# a non-None Dialect; using sqlite avoids contrived suppressions.
_DIALECT = sqlite.dialect()


def test_wire_format_starts_with_version_byte() -> None:
    col = EncryptedType(KEY)
    encoded = col.process_bind_param("hello", _DIALECT)
    raw = base64.b64decode(encoded)
    assert raw[0:1] == b"\x01"


def test_key_id_mismatch_raises_decryption_error() -> None:
    col_a = EncryptedType(KEY, key_id="v1")
    col_b = EncryptedType(KEY, key_id="v2")
    encoded = col_a.process_bind_param("secret", _DIALECT)
    with pytest.raises(DecryptionError, match="Key-id mismatch"):
        col_b.process_result_value(encoded, _DIALECT)


def test_aad_mismatch_raises_decryption_error() -> None:
    col_a = EncryptedType(KEY, associated_data=b"posts.body")
    col_b = EncryptedType(KEY, associated_data=b"users.notes")
    encoded = col_a.process_bind_param("secret", _DIALECT)
    with pytest.raises(DecryptionError):
        col_b.process_result_value(encoded, _DIALECT)


def test_corrupted_version_byte_raises() -> None:
    col = EncryptedType(KEY)
    encoded = col.process_bind_param("hello", _DIALECT)
    raw = base64.b64decode(encoded)
    bad = base64.b64encode(b"\xff" + raw[1:]).decode("ascii")
    with pytest.raises(DecryptionError, match="wire format version"):
        col.process_result_value(bad, _DIALECT)


def test_key_id_default_is_v1() -> None:
    col = EncryptedType(KEY)  # default key_id="v1"
    encoded = col.process_bind_param("x", _DIALECT)
    raw = base64.b64decode(encoded)
    key_id_len = raw[1]
    key_id = raw[2 : 2 + key_id_len]
    assert key_id == b"v1"


def test_invalid_key_id_rejected() -> None:
    with pytest.raises(ValueError, match="key_id"):
        EncryptedType(KEY, key_id="")
    with pytest.raises(ValueError, match="key_id"):
        EncryptedType(KEY, key_id="x" * 33)


def test_round_trip_with_key_id_and_aad() -> None:
    col = EncryptedType(KEY, key_id="prod-2026", associated_data=b"users.email")
    encoded = col.process_bind_param("alice@example.com", _DIALECT)
    out = col.process_result_value(encoded, _DIALECT)
    assert out == "alice@example.com"


def test_iv_is_random_in_random_mode() -> None:
    col = EncryptedType(KEY)
    a = col.process_bind_param("same", _DIALECT)
    b = col.process_bind_param("same", _DIALECT)
    assert a != b  # random IV → different ciphertext


def test_deterministic_mode_same_ciphertext_for_same_plaintext() -> None:
    col = EncryptedType(KEY, deterministic=True)
    a = col.process_bind_param("same", _DIALECT)
    b = col.process_bind_param("same", _DIALECT)
    assert a == b


def test_wrong_key_still_raises() -> None:
    col_a = EncryptedType(KEY)
    col_b = EncryptedType(os.urandom(32))
    encoded = col_a.process_bind_param("hello", _DIALECT)
    with pytest.raises(DecryptionError):
        col_b.process_result_value(encoded, _DIALECT)

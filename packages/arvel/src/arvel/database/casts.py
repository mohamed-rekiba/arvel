"""Custom SQLAlchemy column types: Pydantic, Enum, Encrypted."""

from __future__ import annotations

import base64
import enum
import hashlib
import json
import os
from typing import Any, Generic, TypeVar

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel
from sqlalchemy import JSON, String, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeEngine

from arvel.database.exceptions import DecryptionError

PydanticModelT = TypeVar("PydanticModelT", bound=BaseModel)
EnumT = TypeVar("EnumT", bound=enum.Enum)


class PydanticType(TypeDecorator[PydanticModelT], Generic[PydanticModelT]):
    """Store a Pydantic ``BaseModel`` as JSON / JSONB.

    On PostgreSQL the column is realised as ``JSONB`` (binary, normalised,
    B-tree and GIN indexable). On MySQL the column is native ``JSON``; on
    SQLite it falls back to the JSON1-backed ``TEXT`` representation. The
    dialect choice happens in :meth:`load_dialect_impl` so callers never
    have to think about it — ``unique=True`` and ``index=True`` work on
    every supported backend without operator-class trickery.

    The original instance is reconstructed on load. ``None`` passes through.
    Invalid input raises Pydantic's ``ValidationError`` at bind time —
    never silent persistence of a malformed value.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, model: type[PydanticModelT]) -> None:
        self._model = model
        super().__init__()

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: PydanticModelT | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        return value.model_dump(mode="json")

    def process_result_value(self, value: Any, dialect: Dialect) -> PydanticModelT | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = json.loads(value)
        return self._model.model_validate(value)


class EnumType(TypeDecorator[EnumT], Generic[EnumT]):
    """Store a Python ``Enum`` as its ``.value`` string in the database."""

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: type[EnumT], length: int = 64) -> None:
        self._enum = enum_cls
        super().__init__(length=length)

    def process_bind_param(self, value: EnumT | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, self._enum):
            return value.value
        # Allow string assignment to round-trip (caller may pass raw values).
        return self._enum(value).value

    def process_result_value(self, value: Any, dialect: Dialect) -> EnumT | None:
        if value is None:
            return None
        return self._enum(value)


class EncryptedType(TypeDecorator[str]):
    """AES-256-GCM column encryption.

    Two modes:

    - ``deterministic=False`` (default): random 12-byte IV per write; ciphertext
    shape is ``b64(VERSION || KEY_ID || IV || ciphertext || tag)``. Same
    plaintext → different ciphertext. **Not searchable** by equality.
    - ``deterministic=True``: IV derived from ``HKDF-SHA256(key, plaintext)``,
    so equal plaintexts produce equal ciphertexts. **Searchable** but leaks
    equality. Useful for lookup columns (e.g. hashed-email indexes).

    The wire format is versioned and key-identified so future schemes
    (alternative ciphers, key rotation) can coexist on disk during a rolling
    migration. ``key_id`` defaults to ``"v1"`` and may be any ASCII string up
    to 32 bytes.

    Optional ``associated_data`` is passed to AES-GCM as AAD so ciphertext
    bound to one column won't decrypt against another column even with the
    same key. Recommended pattern is ``EncryptedType(key, associated_data=
    f"{table}.{column}".encode)``.

    Decryption failures (wrong key, tampered ciphertext) raise
    :class:`DecryptionError` — never silent ``None``.
    """

    impl = String
    cache_ok = False

    _AES_256_KEY_BYTES = 32
    _VERSION = b"\x01"  # single-byte format version
    _MAX_KEY_ID_BYTES = 32

    def __init__(
        self,
        key: bytes,
        *,
        deterministic: bool = False,
        key_id: str = "v1",
        associated_data: bytes | None = None,
    ) -> None:
        if len(key) != self._AES_256_KEY_BYTES:
            raise ValueError("EncryptedType key must be 32 bytes (AES-256).")
        key_id_bytes = key_id.encode("ascii")
        if not key_id_bytes or len(key_id_bytes) > self._MAX_KEY_ID_BYTES:
            raise ValueError(
                f"EncryptedType key_id must be 1..{self._MAX_KEY_ID_BYTES} ASCII bytes."
            )
        self._key = key
        self._aes = AESGCM(key)
        self._deterministic = deterministic
        self._key_id_bytes = key_id_bytes
        self._aad = associated_data
        super().__init__(length=2048)

    def _iv(self, plaintext: bytes) -> bytes:
        if self._deterministic:
            return hashlib.sha256(self._key + plaintext).digest()[:12]
        return os.urandom(12)

    def process_bind_param(self, value: str | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        plaintext = value.encode("utf-8")
        iv = self._iv(plaintext)
        ct = self._aes.encrypt(iv, plaintext, associated_data=self._aad)
        # b64( VERSION(1) || KEY_ID_LEN(1) || KEY_ID || IV(12) || CT_with_tag )
        header = self._VERSION + bytes([len(self._key_id_bytes)]) + self._key_id_bytes
        return base64.b64encode(header + iv + ct).decode("ascii")

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        try:
            plaintext = self._decode_and_decrypt(value)
        except DecryptionError:
            raise
        except Exception as exc:  # AESGCM raises InvalidTag (cryptography lib)
            raise DecryptionError(
                "Failed to decrypt column value (wrong key or tampered ciphertext)."
            ) from exc
        return plaintext.decode("utf-8")

    def _decode_and_decrypt(self, value: Any) -> bytes:
        raw = base64.b64decode(value)
        if not raw or raw[0:1] != self._VERSION:
            raise DecryptionError("Unrecognised EncryptedType wire format version.")
        key_id_len = raw[1]
        cursor = 2 + key_id_len
        key_id_on_disk = raw[2:cursor]
        if key_id_on_disk != self._key_id_bytes:
            raise DecryptionError(
                f"Key-id mismatch: ciphertext was written under "
                f"{key_id_on_disk!r}, this column is configured for "
                f"{self._key_id_bytes!r}."
            )
        iv = raw[cursor : cursor + 12]
        ct = raw[cursor + 12 :]
        return self._aes.decrypt(iv, ct, associated_data=self._aad)


__all__ = ["DecryptionError", "EncryptedType", "EnumType", "PydanticType"]

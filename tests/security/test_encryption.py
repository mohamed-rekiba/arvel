"""Tests for AES-256-CBC encryption with HMAC-SHA256."""

from __future__ import annotations

import os

import pytest

from arvel.security.encryption import AesEncrypter
from arvel.security.exceptions import DecryptionError


class TestAesEncrypter:
    def _make_key(self) -> bytes:
        return os.urandom(32)

    def test_encrypt_decrypt_roundtrip(self) -> None:
        key = self._make_key()
        enc = AesEncrypter(key)
        plaintext = "Hello, Arvel!"
        ciphertext = enc.encrypt(plaintext)
        assert enc.decrypt(ciphertext) == plaintext

    def test_different_ciphertext_each_time(self) -> None:
        key = self._make_key()
        enc = AesEncrypter(key)
        c1 = enc.encrypt("same")
        c2 = enc.encrypt("same")
        assert c1 != c2

    def test_tampered_payload_fails(self) -> None:
        key = self._make_key()
        enc = AesEncrypter(key)
        ciphertext = enc.encrypt("secret")

        import base64

        raw = bytearray(base64.urlsafe_b64decode(ciphertext))
        raw[20] ^= 0xFF
        tampered = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")

        with pytest.raises(DecryptionError, match="MAC verification failed"):
            enc.decrypt(tampered)

    def test_wrong_key_fails(self) -> None:
        key1 = self._make_key()
        key2 = self._make_key()
        enc1 = AesEncrypter(key1)
        enc2 = AesEncrypter(key2)
        ciphertext = enc1.encrypt("secret")
        with pytest.raises(DecryptionError):
            enc2.decrypt(ciphertext)

    def test_short_key_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 32 bytes"):
            AesEncrypter(b"short")

    def test_invalid_base64_raises(self) -> None:
        key = self._make_key()
        enc = AesEncrypter(key)
        with pytest.raises(DecryptionError, match="too short"):
            enc.decrypt("dG9vc2hvcnQ=")

    def test_encrypt_empty_string(self) -> None:
        key = self._make_key()
        enc = AesEncrypter(key)
        ciphertext = enc.encrypt("")
        assert enc.decrypt(ciphertext) == ""

    def test_encrypt_unicode(self) -> None:
        key = self._make_key()
        enc = AesEncrypter(key)
        text = "مرحبا بالعالم 🌍"
        assert enc.decrypt(enc.encrypt(text)) == text

    def test_encrypt_long_text(self) -> None:
        key = self._make_key()
        enc = AesEncrypter(key)
        text = "A" * 10000
        assert enc.decrypt(enc.encrypt(text)) == text

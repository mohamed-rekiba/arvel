"""Managers/Security (doc 16) — Encrypter key rotation via MultiFernet. Test-first."""

from __future__ import annotations

from arvel.security import Encrypter


def test_single_key_roundtrip() -> None:
    enc = Encrypter(Encrypter.generate_key())
    assert enc.decrypt(enc.encrypt("hello")) == "hello"


def test_old_ciphertext_decrypts_after_rotation() -> None:
    old_key = Encrypter.generate_key()
    new_key = Encrypter.generate_key()

    token = Encrypter(old_key).encrypt("secret")  # encrypted under the old key

    rotated = Encrypter(new_key, old_key)  # new primary, old kept for decrypt
    assert rotated.decrypt(token) == "secret"  # old ciphertext still readable

    fresh = rotated.encrypt("fresh")
    assert rotated.decrypt(fresh) == "fresh"  # new data uses the new key


def test_rotate_reencrypts_under_primary_key() -> None:
    old_key = Encrypter.generate_key()
    new_key = Encrypter.generate_key()

    token = Encrypter(old_key).encrypt("payload")
    reencrypted = Encrypter(new_key, old_key).rotate(token)

    # the rotated token is now readable by an encrypter holding only the new key
    assert Encrypter(new_key).decrypt(reencrypted) == "payload"

"""03 SEC-CRYPTO — Encrypter: AES-256-GCM, serialize-aware. DR-0032.
See projects/arvel/product/stories/03-sec-crypto.md."""

from __future__ import annotations

import pytest

from arvel.security import DecryptionFailed, Encrypter

# --- object + string round-trips -------------------------------------------------


def test_encrypt_object_roundtrips_the_equal_object() -> None:
    enc = Encrypter(Encrypter.generate_key())
    original = {"a": 1, "b": [1, 2, 3], "c": None}
    token = enc.encrypt(original)
    assert enc.decrypt(token) == original


def test_encrypt_string_roundtrips_and_skips_the_json_envelope() -> None:
    enc = Encrypter(Encrypter.generate_key())
    token = enc.encrypt_string("x")
    assert token != "x"
    assert enc.decrypt_string(token) == "x"


def test_payload_format_is_v1_dot_nonce_dot_ciphertext() -> None:
    enc = Encrypter(Encrypter.generate_key())
    token = enc.encrypt_string("hello")
    version, _nonce, _ct = token.split(".")
    assert version == "v1"


# --- tamper-evidence: a flipped byte must never decrypt -------------------------


def test_flipped_byte_in_ciphertext_raises_decryption_failed() -> None:
    enc = Encrypter(Encrypter.generate_key())
    token = enc.encrypt_string("payload")
    version, nonce_b64, ct_b64 = token.split(".")
    flipped = "A" if ct_b64[0] != "A" else "B"
    tampered = f"{version}.{nonce_b64}.{flipped}{ct_b64[1:]}"
    with pytest.raises(DecryptionFailed):
        enc.decrypt_string(tampered)


def test_flipped_byte_in_nonce_raises_decryption_failed() -> None:
    enc = Encrypter(Encrypter.generate_key())
    token = enc.encrypt_string("payload")
    version, nonce_b64, ct_b64 = token.split(".")
    flipped = "A" if nonce_b64[0] != "A" else "B"
    tampered = f"{version}.{flipped}{nonce_b64[1:]}.{ct_b64}"
    with pytest.raises(DecryptionFailed):
        enc.decrypt_string(tampered)


def test_malformed_payload_raises_decryption_failed_not_a_different_error() -> None:
    enc = Encrypter(Encrypter.generate_key())
    with pytest.raises(DecryptionFailed):
        enc.decrypt_string("garbage")
    with pytest.raises(DecryptionFailed):
        enc.decrypt_string("v1.only-one-more-part")
    with pytest.raises(DecryptionFailed):
        enc.decrypt_string("v2.YWJj.YWJj")  # unsupported version


# --- previous-key decrypt fallback + rotate --------------------------------------


def test_previous_keys_allow_decrypting_old_ciphertext() -> None:
    old_key = Encrypter.generate_key()
    new_key = Encrypter.generate_key()
    token = Encrypter(old_key).encrypt_string("secret")

    rotated_reader = Encrypter(new_key, old_key)
    assert rotated_reader.decrypt_string(token) == "secret"


def test_rotate_reencrypts_under_the_primary_key() -> None:
    old_key = Encrypter.generate_key()
    new_key = Encrypter.generate_key()
    token = Encrypter(old_key).encrypt_string("secret")

    rotated = Encrypter(new_key, old_key).rotate(token)

    assert Encrypter(new_key).decrypt_string(rotated) == "secret"
    with pytest.raises(DecryptionFailed):
        Encrypter(old_key).decrypt_string(rotated)


# --- key parsing / generation ----------------------------------------------------


def test_generate_key_format_is_base64_prefixed() -> None:
    key = Encrypter.generate_key()
    assert key.startswith("base64:")


def test_base64_prefixed_key_is_accepted() -> None:
    key = Encrypter.generate_key()
    enc = Encrypter(key)
    assert enc.decrypt_string(enc.encrypt_string("x")) == "x"


def test_raw_base64_key_without_prefix_is_accepted() -> None:
    import base64

    raw = base64.b64encode(b"0" * 32).decode()  # no "base64:" prefix
    enc = Encrypter(raw)
    assert enc.decrypt_string(enc.encrypt_string("x")) == "x"


def test_wrong_key_length_is_rejected() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Encrypter("base64:dG9vc2hvcnQ=")  # decodes to far fewer than 32 bytes

"""T4.1 — security: Hasher (argon2-cffi/bcrypt driver manager), Encrypter (AES-256-GCM),
Signer (itsdangerous). Deeper hashing/encryption coverage lives in test_security_hashing.py
and test_security_encrypter.py; this file keeps the original cross-cutting smoke tests."""

from __future__ import annotations

import pytest

from arvel.security import DecryptionFailed, Encrypter, Hasher, Signer


def test_hasher_make_and_check() -> None:
    h = Hasher()
    hashed = h.make("s3cret")
    assert hashed.startswith("$argon2")
    assert h.check("s3cret", hashed) is True
    assert h.check("wrong", hashed) is False


def test_encrypter_roundtrip() -> None:
    enc = Encrypter(Encrypter.generate_key())
    token = enc.encrypt("hello")
    assert token != "hello"
    assert enc.decrypt(token) == "hello"


def test_encrypter_rejects_tampered_token() -> None:
    enc = Encrypter(Encrypter.generate_key())
    with pytest.raises(DecryptionFailed):
        enc.decrypt("not-a-valid-token")


def test_signer_sign_unsign() -> None:
    s = Signer("secret-key")
    signed = s.sign({"user": 1})
    assert s.unsign(signed) == {"user": 1}


def test_signer_expiry() -> None:
    from arvel.security import SignatureInvalid

    s = Signer("secret-key")
    signed = s.sign("v")
    with pytest.raises(SignatureInvalid):  # expiry surfaces as the module's own error
        s.unsign(signed, max_age=-1)


def test_security_provider_binds(monkeypatch: pytest.MonkeyPatch) -> None:
    from arvel.kernel import Application, set_application
    from arvel.security.provider import SecurityServiceProvider

    app = Application()
    app.make("config").set("app", {"key": Encrypter.generate_key()})
    SecurityServiceProvider(app).register()
    set_application(app)
    try:
        assert isinstance(app.make("hash"), Hasher)
        assert isinstance(app.make("encrypter"), Encrypter)
        assert isinstance(app.make("signer"), Signer)
    finally:
        set_application(None)

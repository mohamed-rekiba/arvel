"""T4.1 — security: Hasher (pwdlib), Encrypter (Fernet), Signer (itsdangerous)."""

from __future__ import annotations

import pytest

from arvel.security import Encrypter, Hasher, Signer


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
    from cryptography.fernet import InvalidToken

    enc = Encrypter(Encrypter.generate_key())
    with pytest.raises(InvalidToken):
        enc.decrypt("not-a-valid-token")


def test_signer_sign_unsign() -> None:
    s = Signer("secret-key")
    signed = s.sign({"user": 1})
    assert s.unsign(signed) == {"user": 1}


def test_signer_expiry() -> None:
    from itsdangerous import SignatureExpired

    s = Signer("secret-key")
    signed = s.sign("v")
    with pytest.raises(SignatureExpired):
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

"""Cookie encryption (H7): EncryptCookies + emit_cookie + Request.cookie decryption.

Unit-level tests exercise the codec against fakes (same style as ``test_http_session.py``); the
round-trip test drives the real middleware stack through a kernel + ``TestClient`` — the actual
consumer path (scaffold-shaped app, real Set-Cookie on the wire, real second request)."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import EncryptCookies, emit_cookie, reset_sessions
from arvel.http.request import Request
from arvel.kernel import Application, set_application
from arvel.kernel.bootstrap import bootstrap_app
from arvel.routing import Router
from arvel.security import DecryptionFailed, Encrypter


def teardown_function() -> None:
    set_application(None)


# --- emit_cookie -----------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self) -> None:
        self.cookies: list[tuple[str, str, dict[str, Any]]] = []

    def set_cookie(self, key: str, value: str, **kw: Any) -> None:
        self.cookies.append((key, value, kw))


class _CodecRequest:
    """A bare object carrying only ``_cookie_codec`` — enough for emit_cookie/Request.cookie."""

    def __init__(self, codec: Any) -> None:
        self._cookie_codec = codec


def test_emit_cookie_encrypts_when_codec_active_and_name_not_excepted() -> None:
    encrypter = Encrypter(Encrypter.generate_key())
    codec = (encrypter.encrypt_string, encrypter.decrypt_string, ("XSRF-TOKEN",))
    request = _CodecRequest(codec)
    response = _FakeResponse()
    emit_cookie(request, response, "session", "plain-sid", max_age=60)
    name, value, kw = response.cookies[0]
    assert name == "session"
    assert value != "plain-sid"  # ciphertext, not the raw value
    assert encrypter.decrypt_string(value) == "plain-sid"
    assert kw == {"max_age": 60}


def test_emit_cookie_passes_excepted_name_through_plaintext() -> None:
    encrypter = Encrypter(Encrypter.generate_key())
    codec = (encrypter.encrypt_string, encrypter.decrypt_string, ("XSRF-TOKEN",))
    request = _CodecRequest(codec)
    response = _FakeResponse()
    emit_cookie(request, response, "XSRF-TOKEN", "token-value")
    assert response.cookies[0] == ("XSRF-TOKEN", "token-value", {})


def test_emit_cookie_is_plaintext_with_no_active_codec() -> None:
    request = _CodecRequest(None)
    response = _FakeResponse()
    emit_cookie(request, response, "session", "plain-sid")
    assert response.cookies[0] == ("session", "plain-sid", {})


def test_emit_cookie_no_ops_when_response_has_no_set_cookie() -> None:
    emit_cookie(_CodecRequest(None), object(), "session", "plain-sid")  # must not raise


# --- Request.cookie decryption ----------------------------------------------------------------


class _RawWithCookies:
    def __init__(self, cookies: dict[str, str]) -> None:
        self.cookies = cookies


def test_request_cookie_decrypts_through_the_codec() -> None:
    encrypter = Encrypter(Encrypter.generate_key())
    token = encrypter.encrypt_string("the-sid")
    request = Request(_RawWithCookies({"session": token}))
    request._cookie_codec = (encrypter.encrypt_string, encrypter.decrypt_string, ("XSRF-TOKEN",))
    assert request.cookie("session") == "the-sid"


def test_request_cookie_tampered_value_is_treated_as_missing() -> None:
    encrypter = Encrypter(Encrypter.generate_key())
    token = encrypter.encrypt_string("the-sid")
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    request = Request(_RawWithCookies({"session": tampered}))
    request._cookie_codec = (encrypter.encrypt_string, encrypter.decrypt_string, ("XSRF-TOKEN",))
    assert request.cookie("session") is None
    assert request.cookie("session", "fallback") == "fallback"


def test_request_cookie_excepted_name_reads_plaintext() -> None:
    encrypter = Encrypter(Encrypter.generate_key())
    request = Request(_RawWithCookies({"XSRF-TOKEN": "plain-token"}))
    request._cookie_codec = (encrypter.encrypt_string, encrypter.decrypt_string, ("XSRF-TOKEN",))
    assert request.cookie("XSRF-TOKEN") == "plain-token"


def test_request_cookie_absent_returns_default_with_no_codec_lookup() -> None:
    request = Request(_RawWithCookies({}))
    assert request.cookie("session", "d") == "d"


def test_encrypter_decrypt_string_raises_decryption_failed_on_a_malformed_token() -> None:
    encrypter = Encrypter(Encrypter.generate_key())
    try:
        encrypter.decrypt_string("not-a-valid-token")
    except DecryptionFailed:
        pass
    else:  # pragma: no cover - documents the contract emit_cookie/Request.cookie rely on
        raise AssertionError("expected DecryptionFailed")


# --- EncryptCookies.handle: when the codec activates -----------------------------------------


class _Dest:
    def __init__(self) -> None:
        self.seen: Any = None

    async def __call__(self, request: Any) -> str:
        self.seen = getattr(request, "_cookie_codec", None)
        return "ok"


async def test_encrypt_cookies_stashes_nothing_with_no_running_application() -> None:
    dest = _Dest()
    await EncryptCookies().handle(_CodecRequest(None), dest)
    assert dest.seen is None


async def test_encrypt_cookies_stashes_nothing_when_app_key_is_unset() -> None:
    app = Application.configure(".").create()
    bootstrap_app(app)  # registers providers ("encrypter" bound), but no app.key configured
    dest = _Dest()
    await EncryptCookies().handle(_CodecRequest(None), dest)
    assert dest.seen is None


async def test_encrypt_cookies_stashes_a_working_codec_when_app_key_is_set() -> None:
    key = Encrypter.generate_key()
    app = Application.configure(".").with_config({"app": {"key": key}}).create()
    bootstrap_app(app)
    dest = _Dest()
    await EncryptCookies().handle(_CodecRequest(None), dest)
    assert dest.seen is not None
    encrypt, decrypt, except_names = dest.seen
    assert except_names == ("XSRF-TOKEN",)
    assert decrypt(encrypt("round-trip")) == "round-trip"


# --- full round trip through the real middleware stack -----------------------------------------


async def _bump(request: Any) -> dict[str, int]:
    request.session["count"] = request.session.get("count", 0) + 1
    return {"count": request.session["count"]}


def test_session_round_trips_as_ciphertext_and_tamper_yields_a_fresh_session() -> None:
    reset_sessions()
    app = (
        Application.configure(".")
        .with_config({"app": {"key": Encrypter.generate_key()}, "session": {"secure": False}})
        .create()
    )
    bootstrap_app(app)
    try:
        router = Router()
        with router.group(group="web"):
            router.get("/bump", _bump)
        kernel = HttpKernel(app).use_default_groups()
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            first = client.get("/bump")
            assert first.json() == {"count": 1}
            raw_session_cookie = first.cookies.get("session")
            assert raw_session_cookie is not None
            # httpx quotes a cookie value containing special chars (base64's "/") on read-back
            session_cookie = raw_session_cookie.strip('"')
            assert session_cookie.startswith("v1.")  # ciphertext on the wire, not the raw sid

            xsrf_cookie = first.cookies.get("XSRF-TOKEN")
            assert xsrf_cookie is not None
            assert not xsrf_cookie.strip('"').startswith("v1.")  # excepted — stays plaintext

            # same client -> cookie jar carries the session cookie automatically: persists
            second = client.get("/bump")
            assert second.json() == {"count": 2}

            # a tampered cookie fails closed to a FRESH session, not a 500
            client.cookies.set(
                "session", session_cookie[:-1] + ("A" if session_cookie[-1] != "A" else "B")
            )
            third = client.get("/bump")
            assert third.status_code == 200
            assert third.json() == {"count": 1}
    finally:
        set_application(None)

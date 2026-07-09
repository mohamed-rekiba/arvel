"""E9: the five additive ``PendingRequest`` peripherals — ``without_redirects``,
``without_verify``, ``sink``, ``with_url_parameters``, ``macro`` (spec E9, DR-0043)."""

from __future__ import annotations

import datetime
import ipaddress
import ssl
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from arvel.client import Client, PendingRequest

# --- without_redirects / default-follows -------------------------------------------------


def _redirect_transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/a":
            return httpx.Response(302, headers={"Location": "/b"})
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


async def test_default_now_follows_redirects() -> None:
    calls: list[str] = []
    client = Client(transport=_redirect_transport(calls))
    try:
        response = await client.get("https://x.test/a")
        assert response.status() == 200
        assert response.json() == {"ok": True}
        assert calls == ["/a", "/b"]
    finally:
        await client.aclose()


async def test_without_redirects_stops_at_the_3xx() -> None:
    calls: list[str] = []
    client = Client(transport=_redirect_transport(calls))
    try:
        response = await client.without_redirects().get("https://x.test/a")
        assert response.status() == 302
        assert response.header("Location") == "/b"
        assert calls == ["/a"]  # /b was never requested
    finally:
        await client.aclose()


# --- without_verify ------------------------------------------------------------------------


def _self_signed_cert(directory: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(minutes=5))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "cert.pem"
    key_path = directory / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # quiet: don't spam test output
        pass


@pytest.fixture
def self_signed_https_url(tmp_path: Path) -> Iterator[str]:
    """A local HTTPS server on a self-signed cert — real TLS, no external infra."""
    cert_path, key_path = _self_signed_cert(tmp_path)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    httpd = HTTPServer(("127.0.0.1", 0), _OkHandler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{httpd.server_port}/"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


async def test_without_verify_completes_against_a_self_signed_server(
    self_signed_https_url: str,
) -> None:
    client = Client()  # real network path — no fake, no custom transport
    try:
        with pytest.raises(httpx.TransportError):  # default verify=True: untrusted cert rejected
            await client.get(self_signed_https_url)
        # no-verify succeeds — and it can only succeed by *not* going through the (verify=True)
        # shared client used above, which would reject the same cert the same way.
        response = await client.without_verify().get(self_signed_https_url)
        assert response.status() == 200
        assert response.body() == "ok"
    finally:
        await client.aclose()


# --- sink -----------------------------------------------------------------------------------


async def test_sink_streams_the_body_to_a_file_without_buffering_it_whole(tmp_path: Path) -> None:
    body = b"chunk-me" * 4096  # large enough to span multiple stream chunks

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    client = Client(transport=httpx.MockTransport(handler))
    dest = tmp_path / "download.bin"
    try:
        response = await client.sink(dest).get("https://x.test/file")
        assert response.status() == 200
        assert dest.read_bytes() == body
    finally:
        await client.aclose()


# --- with_url_parameters ---------------------------------------------------------------------


async def test_with_url_parameters_substitutes_tokens_before_send() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    try:
        response = await client.with_url_parameters({"id": 5}).get("https://x.test/users/{id}")
        assert response.status() == 200
        assert seen["url"] == "https://x.test/users/5"
    finally:
        await client.aclose()


async def test_with_url_parameters_missing_param_raises_and_never_sends() -> None:
    sent = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent = True
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match=r"\{id\}"):
            await client.with_url_parameters({}).get("https://x.test/users/{id}")
        assert sent is False
    finally:
        await client.aclose()


# --- macro ------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_macro_registry() -> Iterator[None]:
    """`_macros` is a class-level (process-global) registry — never leak a test's macro."""
    before = set(PendingRequest._macros)
    yield
    for name in set(PendingRequest._macros) - before:
        del PendingRequest._macros[name]


async def test_macro_registered_then_called_on_a_freshly_constructed_client() -> None:
    effects: list[str] = []

    def as_probe(pending: PendingRequest, tag: str) -> PendingRequest:
        effects.append(tag)
        return pending

    Client().macro("as_probe", as_probe)

    fresh = Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    try:
        response = await fresh.as_probe("hello").get("https://x.test/")
        assert response.status() == 200
        assert effects == ["hello"]
    finally:
        await fresh.aclose()


async def test_unregistered_attribute_still_raises_attribute_error() -> None:
    client = Client()
    with pytest.raises(AttributeError):
        client.definitely_not_a_real_thing_or_macro


def test_url_parameter_value_is_not_re_substituted() -> None:
    # a value that itself looks like a token must be injected once, never re-expanded
    pending = Client().with_url_parameters({"a": "{b}", "b": "X"})
    assert pending._apply_url_parameters("/x/{a}/{b}") == "/x/{b}/X"


def test_client_underscore_attribute_raises_not_recurses() -> None:
    with pytest.raises(AttributeError):
        Client()._definitely_missing  # underscore names never route to macros

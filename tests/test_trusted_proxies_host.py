"""ch04 / finding A1 — TrustProxies (config-gated forwarded headers on Request) + ValidateHost
(400 on an untrusted Host). Forwarded headers are honored only when config('app.trusted_proxies')
trusts the peer; Host is validated against config('app.trusted_hosts') when set."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import ValidateHost
from arvel.http.request import Request
from arvel.kernel.application import Application
from arvel.routing import Router


class _URL:
    def __init__(self, scheme: str = "http", hostname: str = "app.test") -> None:
        self.scheme = scheme
        self.hostname = hostname


class _Client:
    def __init__(self, host: str) -> None:
        self.host = host


class _Req:
    def __init__(self, headers: dict[str, str], peer: str, scheme: str) -> None:
        self.headers = headers
        self.client = _Client(peer)
        self.url = _URL(scheme)


def _req(headers: dict[str, str], peer: str = "10.0.0.1", scheme: str = "http") -> Request:
    return Request(_Req(headers, peer, scheme))


def _app(app_cfg: dict[str, Any]) -> Application:
    return Application.configure().with_config({"app": app_cfg}).create()


# --- TrustProxies (Request) ------------------------------------------------
def test_ip_ignores_forwarded_when_untrusted() -> None:
    _app({})
    assert _req({"x-forwarded-for": "1.2.3.4"}, peer="10.0.0.1").ip() == "10.0.0.1"


def test_ip_uses_forwarded_when_trust_all() -> None:
    _app({"trusted_proxies": "*"})
    assert _req({"x-forwarded-for": "1.2.3.4, 5.6.7.8"}).ip() == "1.2.3.4"


def test_ip_trusts_only_listed_peer() -> None:
    _app({"trusted_proxies": ["10.0.0.1"]})
    assert _req({"x-forwarded-for": "1.2.3.4"}, peer="10.0.0.1").ip() == "1.2.3.4"
    assert _req({"x-forwarded-for": "1.2.3.4"}, peer="9.9.9.9").ip() == "9.9.9.9"


def test_scheme_and_secure_via_forwarded_proto() -> None:
    _app({"trusted_proxies": "*"})
    r = _req({"x-forwarded-proto": "https"}, scheme="http")
    assert r.scheme() == "https"
    assert r.is_secure() is True


def test_host_prefers_forwarded_when_trusted() -> None:
    _app({"trusted_proxies": "*"})
    r = _req({"x-forwarded-host": "public.example.com:443", "host": "internal:8000"})
    assert r.host() == "public.example.com"


def test_host_from_header_when_untrusted() -> None:
    _app({})
    r = _req({"x-forwarded-host": "evil.com", "host": "app.test:8000"})
    assert r.host() == "app.test"


# --- ValidateHost (global middleware) --------------------------------------
async def _ok(request: Any) -> dict[str, str]:
    return {"ok": "1"}


def _client(trusted_hosts: Any) -> TestClient[Any]:
    app = Application.configure().with_config({"app": {"trusted_hosts": trusted_hosts}}).create()
    router = Router()
    router.get("/", _ok)
    kernel = HttpKernel(app=app)
    kernel.global_middleware.append(ValidateHost)
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_validate_host_rejects_untrusted() -> None:
    with _client(["good.test"]) as client:
        assert client.get("/", headers={"Host": "evil.test"}).status_code == 400


def test_validate_host_allows_trusted() -> None:
    with _client(["good.test"]) as client:
        assert client.get("/", headers={"Host": "good.test"}).json() == {"ok": "1"}


def test_validate_host_noop_when_unset() -> None:
    with _client(None) as client:
        assert client.get("/", headers={"Host": "anything.test"}).status_code == 200


def test_use_default_global_wires_validate_host() -> None:
    kernel = HttpKernel().use_default_global()
    assert ValidateHost in kernel.global_middleware
    kernel.use_default_global()
    assert kernel.global_middleware.count(ValidateHost) == 1

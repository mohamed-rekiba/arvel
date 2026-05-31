"""Generic OIDC provider — discovery, trailing slash, and failure handling."""

from __future__ import annotations

import httpx
import pytest
from arvel_auth_social.exceptions import OIDCDiscoveryError
from arvel_auth_social.providers import OIDCProvider
from tests.support import mock_client

_DOC = {
    "authorization_endpoint": "https://idp.test/authorize",
    "token_endpoint": "https://idp.test/token",
    "userinfo_endpoint": "https://idp.test/userinfo",
}


async def test_discovery_populates_endpoints() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_DOC)

    provider = await OIDCProvider.discover(
        issuer="https://idp.test",
        client_id="cid",
        client_secret="sec",
        redirect_uri="https://app.test/cb",
        http_client=mock_client(handler),
    )
    assert provider.authorize_url == _DOC["authorization_endpoint"]
    assert provider.token_url == _DOC["token_endpoint"]
    assert provider.userinfo_url == _DOC["userinfo_endpoint"]
    assert seen == ["https://idp.test/.well-known/openid-configuration"]


async def test_discovery_handles_trailing_slash() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_DOC)

    await OIDCProvider.discover(
        issuer="https://idp.test/",
        client_id="c",
        client_secret="s",
        redirect_uri="https://app.test/cb",
        http_client=mock_client(handler),
    )
    assert "//.well-known" not in seen[0]
    assert seen == ["https://idp.test/.well-known/openid-configuration"]


async def test_discovery_unreachable_raises_with_status() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(OIDCDiscoveryError, match="HTTP 503"):
        await OIDCProvider.discover(
            issuer="https://idp.test",
            client_id="c",
            client_secret="s",
            redirect_uri="https://app.test/cb",
            http_client=mock_client(handler),
        )


async def test_http_issuer_rejected_by_default() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        return httpx.Response(200, json=_DOC)

    with pytest.raises(OIDCDiscoveryError, match="https"):
        await OIDCProvider.discover(
            issuer="http://idp.test",
            client_id="c",
            client_secret="s",
            redirect_uri="https://app.test/cb",
            http_client=mock_client(handler),
        )


async def test_http_issuer_allowed_when_opted_in() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_DOC)

    provider = await OIDCProvider.discover(
        issuer="http://idp.test",
        client_id="c",
        client_secret="s",
        redirect_uri="https://app.test/cb",
        allow_http=True,
        http_client=mock_client(handler),
    )
    assert provider.token_url == _DOC["token_endpoint"]

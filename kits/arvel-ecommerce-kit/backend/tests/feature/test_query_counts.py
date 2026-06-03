"""Query-count guards for the storefront read path.

The storefront lists products from the materialized catalog view and attaches
one media row per product. Without batch loading that's a classic N+1: one query
per product to fetch its media. These tests pin the media-query count to a small
constant so a regression reintroducing per-row media loads fails loudly.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from tests.conftest import (
        MailpitEndpoint,
        MinioEndpoint,
        RabbitmqEndpoint,
        RedisEndpoint,
    )

_MEDIA_FROM_RE = re.compile(r"\bfrom\s+media\b", re.IGNORECASE)
_CATALOG_FROM_RE = re.compile(r"\bfrom\s+products_catalog\b", re.IGNORECASE)


@pytest.fixture
async def app(
    fresh_db: str,
    redis_endpoint: RedisEndpoint,
    rabbitmq_endpoint: RabbitmqEndpoint,
    minio_endpoint: MinioEndpoint,
    mailpit_endpoint: MailpitEndpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    monkeypatch.setenv("DB_URL", fresh_db)
    monkeypatch.setenv("CACHE_URL", redis_endpoint.url)
    monkeypatch.setenv("AMQP_URL", rabbitmq_endpoint.amqp_url)
    monkeypatch.setenv("S3_ENDPOINT", minio_endpoint.endpoint_url)
    monkeypatch.setenv("S3_ACCESS_KEY", minio_endpoint.access_key)
    monkeypatch.setenv("S3_SECRET_KEY", minio_endpoint.secret_key)
    monkeypatch.setenv("S3_BUCKET", minio_endpoint.bucket)
    monkeypatch.setenv("MAIL_HOST", mailpit_endpoint.smtp_host)
    monkeypatch.setenv("MAIL_PORT", str(mailpit_endpoint.smtp_port))
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_KEY", "query-count-test-key-must-be-32-bytes-or-more!")

    from app.bootstrap import create_app

    application = await create_app()
    await application.seed("catalog")
    try:
        yield application
    finally:
        await application.shutdown()


@pytest.fixture
async def client(app: Any) -> Any:
    import importlib

    httpx: Any = importlib.import_module("httpx")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as c:
        yield c


def _media_select_count(log: list[dict[str, Any]]) -> int:
    return sum(1 for entry in log if _MEDIA_FROM_RE.search(str(entry["sql"])))


def _catalog_select_count(log: list[dict[str, Any]]) -> int:
    return sum(1 for entry in log if _CATALOG_FROM_RE.search(str(entry["sql"])))


async def _login(client: Any, email: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, f"Login failed for {email}: {response.json()}"
    return str(response.json()["access_token"])


@pytest.mark.asyncio
async def test_storefront_listing_does_not_n_plus_one_media(client: Any) -> None:
    """Listing 20 products must fetch their media in a bounded number of queries."""
    from arvel.database.db import DB

    # Warm any first-request setup so it doesn't pollute the measured window.
    warm = await client.get("/api/products?limit=20")
    assert warm.status_code == 200
    product_count = len(warm.json()["data"])
    assert product_count >= 5, "Need several products to make the N+1 measurement meaningful"

    DB.enable_query_log()
    try:
        DB.flush_query_log()
        response = await client.get("/api/products?limit=20")
        assert response.status_code == 200
        log = DB.get_query_log()
    finally:
        DB.disable_query_log()

    media_queries = _media_select_count(log)
    assert media_queries <= 2, (
        f"Storefront listed {product_count} products but issued {media_queries} media "
        f"queries — expected a single batched load (N+1 regression)."
    )


@pytest.mark.asyncio
async def test_storefront_search_does_not_n_plus_one_media(client: Any) -> None:
    """Search results must batch media loads just like the listing."""
    from arvel.database.db import DB

    warm = await client.get("/api/search?q=pro")
    assert warm.status_code == 200

    DB.enable_query_log()
    try:
        DB.flush_query_log()
        response = await client.get("/api/search?q=pro")
        assert response.status_code == 200
        log = DB.get_query_log()
    finally:
        DB.disable_query_log()

    media_queries = _media_select_count(log)
    assert media_queries <= 2, (
        f"Search issued {media_queries} media queries — expected a single batched load."
    )


@pytest.mark.asyncio
async def test_cart_does_not_n_plus_one_media_or_catalog(client: Any) -> None:
    """Rendering a cart with several items must batch catalog + media loads.

    The naive path fetched one ProductCatalog row AND one media row per cart
    item (2N queries). The cart should instead issue one batched catalog query
    and one batched media query regardless of item count.
    """
    from arvel.database.db import DB

    token = await _login(client, "customer@example.com", "password")
    headers = {"Authorization": f"Bearer {token}"}

    listing = await client.get("/api/products?limit=5")
    assert listing.status_code == 200
    product_ids = [p["id"] for p in listing.json()["data"]][:5]
    assert len(product_ids) >= 3, "Need several distinct products to measure the cart N+1"

    for pid in product_ids:
        added = await client.post(
            "/api/cart/items", headers=headers, json={"product_id": pid, "quantity": 1}
        )
        assert added.status_code == 200

    DB.enable_query_log()
    try:
        DB.flush_query_log()
        response = await client.get("/api/cart", headers=headers)
        assert response.status_code == 200
        log = DB.get_query_log()
    finally:
        DB.disable_query_log()

    item_count = len(response.json()["data"]["items"])
    assert item_count >= 3

    media_queries = _media_select_count(log)
    assert media_queries <= 2, (
        f"Cart with {item_count} items issued {media_queries} media queries — "
        f"expected a single batched load (N+1 regression)."
    )
    catalog_queries = _catalog_select_count(log)
    assert catalog_queries <= 2, (
        f"Cart with {item_count} items issued {catalog_queries} products_catalog queries — "
        f"expected one batched lookup, not one per item (N+1 regression)."
    )

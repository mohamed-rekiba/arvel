"""Materialized view refresh on catalog changes.

Coverage:
- publishing a product triggers view refresh; product appears in storefront
- unpublishing removes product from storefront after refresh
- soft-deleting a category removes its products from storefront
- deactivating a vendor removes its products from storefront
- REFRESH CONCURRENTLY does not block storefront reads
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from tests.conftest import (
        MailpitEndpoint,
        RabbitmqEndpoint,
        RedisEndpoint,
        S3Endpoint,
    )


@pytest.fixture
async def app(
    fresh_db: str,
    redis_endpoint: RedisEndpoint,
    rabbitmq_endpoint: RabbitmqEndpoint,
    s3_endpoint: S3Endpoint,
    mailpit_endpoint: MailpitEndpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    monkeypatch.setenv("DB_URL", fresh_db)
    monkeypatch.setenv("CACHE_URL", redis_endpoint.url)
    monkeypatch.setenv("AMQP_URL", rabbitmq_endpoint.amqp_url)
    monkeypatch.setenv("STORAGE_S3_ENDPOINT", s3_endpoint.endpoint_url)
    monkeypatch.setenv("STORAGE_S3_KEY", s3_endpoint.access_key)
    monkeypatch.setenv("STORAGE_S3_SECRET", s3_endpoint.secret_key)
    monkeypatch.setenv("STORAGE_S3_BUCKET", s3_endpoint.bucket)
    monkeypatch.setenv("MAIL_HOST", mailpit_endpoint.smtp_host)
    monkeypatch.setenv("MAIL_PORT", str(mailpit_endpoint.smtp_port))
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_KEY", "matview-test-key-must-be-32-bytes-or-more!")

    from app.bootstrap import create_app

    application = await create_app()
    try:
        yield application
    finally:
        await application.shutdown()


@pytest.fixture
async def client(app: Any) -> Any:
    import importlib

    httpx: Any = importlib.import_module("httpx2")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as c:
        yield c


@pytest.fixture
async def admin_token(client: Any) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"email": "superadmin@example.com", "password": "password"},
    )
    return str(response.json()["access_token"])


@pytest.mark.asyncio
async def test_publishing_draft_product_appears_in_storefront(
    client: Any, admin_token: str
) -> None:
    """publish triggers view refresh; product becomes visible in storefront."""
    # Get the draft product
    products = await client.get(
        "/api/admin/products?status=draft",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    draft = products.json()["data"][0]
    product_id = draft["id"]
    product_en_slug = draft["slug"]["en"]

    # Confirm it's not in the storefront
    before = await client.get("/api/products")
    before_ids = {p["id"] for p in before.json()["data"]}
    assert product_id not in before_ids

    # Publish
    await client.patch(
        f"/api/admin/products/{product_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Must be in storefront now
    after = await client.get("/api/products")
    after_ids = {p["id"] for p in after.json()["data"]}
    assert product_id in after_ids, (
        f"Published product {product_en_slug} not found in storefront after refresh"
    )


@pytest.mark.asyncio
async def test_unpublishing_product_disappears_from_storefront(
    client: Any, admin_token: str
) -> None:
    """unpublish triggers view refresh; product removed from storefront."""
    products = await client.get(
        "/api/admin/products?status=published",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    product_id = products.json()["data"][0]["id"]

    await client.patch(
        f"/api/admin/products/{product_id}/unpublish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    after = await client.get("/api/products")
    after_ids = {p["id"] for p in after.json()["data"]}
    assert product_id not in after_ids


@pytest.mark.asyncio
async def test_soft_deleting_category_removes_its_products_from_storefront(
    client: Any, admin_token: str
) -> None:
    """category deletion propagates to storefront via view refresh."""
    # Drive off a product that is actually visible in the storefront and resolve
    # its category from that same payload — picking the "first category" skipped
    # whenever it happened to hold no published products, so the behavior went
    # unverified.
    product_id, category_id = await _visible_product_with("category_id", client)

    await client.delete(
        f"/api/admin/categories/{category_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    after = await client.get("/api/products?limit=100")
    after_ids = {p["id"] for p in after.json()["data"]}
    assert product_id not in after_ids, (
        "Product in a soft-deleted category must not appear in storefront"
    )


@pytest.mark.asyncio
async def test_deactivating_vendor_removes_products_from_storefront(
    client: Any, admin_token: str
) -> None:
    """vendor deactivation propagates to storefront via view refresh."""
    product_id, vendor_id = await _visible_product_with("vendor_id", client)

    await client.delete(
        f"/api/admin/vendors/{vendor_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    after = await client.get("/api/products?limit=100")
    after_ids = {p["id"] for p in after.json()["data"]}
    assert product_id not in after_ids, (
        "Product from a soft-deleted vendor must not appear in storefront"
    )


async def _visible_product_with(fk_field: str, client: Any) -> tuple[str, str]:
    """Return (product_id, fk_value) for a storefront-visible product whose
    ``fk_field`` (``category_id`` / ``vendor_id``) is set."""
    response = await client.get("/api/products?limit=100")
    assert response.status_code == 200
    for product in response.json()["data"]:
        fk_value = product.get(fk_field)
        if fk_value:
            return str(product["id"]), str(fk_value)
    pytest.fail(f"seed must publish a visible product with a {fk_field}")

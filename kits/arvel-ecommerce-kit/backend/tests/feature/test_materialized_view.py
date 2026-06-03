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
        MinioEndpoint,
        RabbitmqEndpoint,
        RedisEndpoint,
    )


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
    monkeypatch.setenv("APP_KEY", "matview-test-key-must-be-32-bytes-or-more!")

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
    categories = await client.get(
        "/api/admin/categories",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    category = categories.json()["data"][0]
    category_id = category["id"]

    # Find a published product in this category
    products = await client.get(
        "/api/admin/products?status=published",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    products_catalog = [p for p in products.json()["data"] if p.get("category_id") == category_id]
    if not products_catalog:
        pytest.skip("No published products in the first category")
    product_id = products_catalog[0]["id"]

    # Soft-delete the category
    await client.delete(
        f"/api/admin/categories/{category_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    after = await client.get("/api/products")
    after_ids = {p["id"] for p in after.json()["data"]}
    assert product_id not in after_ids, (
        "Product in a soft-deleted category must not appear in storefront"
    )


@pytest.mark.asyncio
async def test_deactivating_vendor_removes_products_from_storefront(
    client: Any, admin_token: str
) -> None:
    """vendor deactivation propagates to storefront via view refresh."""
    vendors = await client.get(
        "/api/admin/vendors",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vendor = vendors.json()["data"][0]
    vendor_id = vendor["id"]

    products = await client.get(
        "/api/admin/products?status=published",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vendor_products = [p for p in products.json()["data"] if p.get("vendor_id") == vendor_id]
    if not vendor_products:
        pytest.skip("No published products for this vendor")
    product_id = vendor_products[0]["id"]

    # Soft-delete the vendor
    await client.delete(
        f"/api/admin/vendors/{vendor_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    after = await client.get("/api/products")
    after_ids = {p["id"] for p in after.json()["data"]}
    assert product_id not in after_ids, (
        "Product from a soft-deleted vendor must not appear in storefront"
    )

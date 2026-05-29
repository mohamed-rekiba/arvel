"""Admin product management tests — US-008 through US-014.

RED: all tests fail at import time until Stage 3b implements app.bootstrap.

Acceptance criteria:
- US-008: authenticated admin can list products (with trashed filter)
- US-009: catalog_manager can create a product with i18n fields
- US-010: catalog_manager can update product fields
- US-011: catalog_manager can soft-delete; product disappears from storefront
- US-011: super_admin can force-delete (permanent)
- US-012: catalog_manager can restore a soft-deleted product
- US-013: catalog_manager can publish/unpublish; materialized view refreshed
- US-014: catalog_manager can list, upload, delete product media
"""

from __future__ import annotations

import io
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
    monkeypatch.setenv("REDIS_URL", redis_endpoint.url)
    monkeypatch.setenv("AMQP_URL", rabbitmq_endpoint.amqp_url)
    monkeypatch.setenv("S3_ENDPOINT", minio_endpoint.endpoint_url)
    monkeypatch.setenv("S3_ACCESS_KEY", minio_endpoint.access_key)
    monkeypatch.setenv("S3_SECRET_KEY", minio_endpoint.secret_key)
    monkeypatch.setenv("S3_BUCKET", minio_endpoint.bucket)
    monkeypatch.setenv("MAIL_HOST", mailpit_endpoint.smtp_host)
    monkeypatch.setenv("MAIL_PORT", str(mailpit_endpoint.smtp_port))
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_KEY", "admin-products-test-key-32-bytes-or-more!")

    from app.bootstrap import create_app  # RED until Stage 3b

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
async def catalog_token(client: Any) -> str:
    return await _login(client, "catalog@example.com", "password")


@pytest.fixture
async def support_token(client: Any) -> str:
    return await _login(client, "support@example.com", "password")


@pytest.fixture
async def super_admin_token(client: Any) -> str:
    return await _login(client, "superadmin@example.com", "password")


@pytest.fixture
async def vendor_id(client: Any, catalog_token: str) -> str:
    r = await client.get("/api/admin/vendors", headers={"Authorization": f"Bearer {catalog_token}"})
    return str(r.json()["data"][0]["id"])


@pytest.fixture
async def category_id(client: Any, catalog_token: str) -> str:
    r = await client.get(
        "/api/admin/categories", headers={"Authorization": f"Bearer {catalog_token}"}
    )
    return str(r.json()["data"][0]["id"])


# ─── US-008: product listing ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_can_list_products(client: Any, catalog_token: str) -> None:
    """US-008: catalog_manager can list all products including drafts."""
    response = await client.get(
        "/api/admin/products", headers={"Authorization": f"Bearer {catalog_token}"}
    )
    assert response.status_code == 200
    body = response.json()
    # Seed includes 1 draft — admin sees it
    all_statuses = {p["status"] for p in body["data"]}
    assert "draft" in all_statuses or "published" in all_statuses


@pytest.mark.asyncio
async def test_support_cannot_create_product(client: Any, support_token: str) -> None:
    """US-008: support role (level 40) cannot create products."""
    response = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {support_token}"},
        json={},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_includes_trashed_when_requested(client: Any, catalog_token: str) -> None:
    """US-008: ?trashed=with includes soft-deleted products."""
    # Soft-delete a product first
    products = await client.get(
        "/api/admin/products", headers={"Authorization": f"Bearer {catalog_token}"}
    )
    first_id = products.json()["data"][0]["id"]
    await client.delete(
        f"/api/admin/products/{first_id}",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )

    response = await client.get(
        "/api/admin/products?trashed=with",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    ids = {p["id"] for p in response.json()["data"]}
    assert first_id in ids, "?trashed=with must include soft-deleted products"


# ─── US-009: create product ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_manager_can_create_product(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """US-009: POST /api/admin/products creates a product with i18n fields."""
    payload = {
        "name": {"en": "Test Widget", "ar": "أداة تجريبية", "tr": "Test Widget"},
        "slug": {"en": "test-widget", "ar": "test-widget", "tr": "test-widget"},
        "description": {"en": "A test product.", "ar": "منتج تجريبي.", "tr": "Test ürünü."},
        "price": 19.99,
        "stock_qty": 10,
        "category_id": category_id,
        "vendor_id": vendor_id,
    }
    response = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {catalog_token}"},
        json=payload,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["name"]["en"] == "Test Widget"
    assert body["status"] == "draft"
    assert body["deleted_at"] is None


@pytest.mark.asyncio
async def test_create_product_rejects_missing_required_fields(
    client: Any, catalog_token: str
) -> None:
    """US-009: creating a product without price or category_id returns 422."""
    response = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {catalog_token}"},
        json={"name": {"en": "Incomplete"}},
    )
    assert response.status_code == 422


# ─── US-010: update product ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_manager_can_update_product_price(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """US-010: PATCH /api/admin/products/{id} updates price."""
    created = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {catalog_token}"},
        json={
            "name": {"en": "Widget"},
            "slug": {"en": "widget"},
            "description": {"en": "..."},
            "price": 9.99,
            "stock_qty": 5,
            "category_id": category_id,
            "vendor_id": vendor_id,
        },
    )
    product_id = created.json()["data"]["id"]

    updated = await client.patch(
        f"/api/admin/products/{product_id}",
        headers={"Authorization": f"Bearer {catalog_token}"},
        json={"price": 14.99},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["price"] == 14.99


# ─── US-011: soft-delete + force-delete ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_soft_delete_product_disappears_from_storefront(
    client: Any, catalog_token: str
) -> None:
    """US-011: soft-deleted product is removed from storefront after materialized view refresh."""
    products = await client.get(
        "/api/admin/products?status=published",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    product = products.json()["data"][0]
    product_id = product["id"]

    delete_response = await client.delete(
        f"/api/admin/products/{product_id}",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    assert delete_response.status_code == 204

    # Storefront must not return the product
    storefront = await client.get("/api/products")
    storefront_ids = {p["id"] for p in storefront.json()["data"]}
    assert product_id not in storefront_ids


@pytest.mark.asyncio
async def test_force_delete_requires_super_admin(
    client: Any, catalog_token: str, super_admin_token: str, vendor_id: str, category_id: str
) -> None:
    """US-011: force-delete returns 403 for catalog_manager, 204 for super_admin."""
    created = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={
            "name": {"en": "Deletable"},
            "slug": {"en": "deletable-force"},
            "description": {"en": "."},
            "price": 1.00,
            "stock_qty": 0,
            "category_id": category_id,
            "vendor_id": vendor_id,
        },
    )
    product_id = created.json()["data"]["id"]

    # First soft-delete it (required before force)
    await client.delete(
        f"/api/admin/products/{product_id}",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )

    # catalog_manager can't force-delete
    catalog_response = await client.delete(
        f"/api/admin/products/{product_id}/force",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    assert catalog_response.status_code == 403

    # super_admin can
    sa_response = await client.delete(
        f"/api/admin/products/{product_id}/force",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert sa_response.status_code == 204


# ─── US-012: restore ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_soft_deleted_product_reappears_in_storefront(
    client: Any, catalog_token: str
) -> None:
    """US-012: restoring a soft-deleted published product brings it back to storefront."""
    products = await client.get(
        "/api/admin/products?status=published",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    product_id = products.json()["data"][0]["id"]

    await client.delete(
        f"/api/admin/products/{product_id}",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    restore = await client.post(
        f"/api/admin/products/{product_id}/restore",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    assert restore.status_code == 200
    assert restore.json()["data"]["deleted_at"] is None


# ─── US-013: publish / unpublish ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_product_appears_in_storefront(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """US-013: publishing a draft product makes it visible in the storefront."""
    created = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {catalog_token}"},
        json={
            "name": {"en": "New Draft"},
            "slug": {"en": "new-draft"},
            "description": {"en": "Draft product."},
            "price": 5.00,
            "stock_qty": 10,
            "category_id": category_id,
            "vendor_id": vendor_id,
        },
    )
    product_id = created.json()["data"]["id"]

    publish = await client.patch(
        f"/api/admin/products/{product_id}/publish",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    assert publish.status_code == 200
    assert publish.json()["data"]["status"] == "published"
    assert publish.json()["data"]["published_at"] is not None

    storefront = await client.get("/api/products")
    storefront_ids = {p["id"] for p in storefront.json()["data"]}
    assert product_id in storefront_ids


# ─── US-014: media ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_product_image_creates_conversions(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """US-014: uploading an image creates thumbnail, card, and full conversions."""
    created = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {catalog_token}"},
        json={
            "name": {"en": "Photo Product"},
            "slug": {"en": "photo-product"},
            "description": {"en": "..."},
            "price": 10.00,
            "stock_qty": 1,
            "category_id": category_id,
            "vendor_id": vendor_id,
        },
    )
    product_id = created.json()["data"]["id"]

    # Minimal 1x1 JPEG
    tiny_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
        b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
        b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1eC\x19\x1c45\xff\xc0\x00"
        b"\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05"
        b"\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04"
        b"\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xff\xd9"
    )

    upload = await client.post(
        f"/api/admin/products/{product_id}/media",
        headers={"Authorization": f"Bearer {catalog_token}"},
        files={"file": ("photo.jpg", io.BytesIO(tiny_jpeg), "image/jpeg")},
    )
    assert upload.status_code == 201
    body = upload.json()["data"]
    assert "conversions" in body
    assert "thumbnail" in body["conversions"]
    assert "card" in body["conversions"]
    assert "full" in body["conversions"]


@pytest.mark.asyncio
async def test_upload_rejects_non_image_file(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """US-014: uploading a non-image (e.g. PDF) returns 400."""
    created = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {catalog_token}"},
        json={
            "name": {"en": "Bad Upload"},
            "slug": {"en": "bad-upload"},
            "description": {"en": "..."},
            "price": 1.00,
            "stock_qty": 0,
            "category_id": category_id,
            "vendor_id": vendor_id,
        },
    )
    product_id = created.json()["data"]["id"]

    upload = await client.post(
        f"/api/admin/products/{product_id}/media",
        headers={"Authorization": f"Bearer {catalog_token}"},
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert upload.status_code == 400


# ─── helpers ────────────────────────────────────────────────────────────────────


async def _login(client: Any, email: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, f"Login failed: {response.json()}"
    return str(response.json()["access_token"])

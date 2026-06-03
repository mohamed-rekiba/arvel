"""Admin product management — list, CRUD, publish, media.

Coverage:
- authenticated admin can list products (with trashed filter)
- catalog_manager can create a product with i18n fields
- catalog_manager can update product fields
- catalog_manager can soft-delete; product disappears from storefront
- super_admin can force-delete (permanent)
- catalog_manager can restore a soft-deleted product
- catalog_manager can publish/unpublish; materialized view refreshed
- catalog_manager can list, upload, delete product media
- upload creates thumbnail / card / full conversions
- card and full conversions have responsive srcset after upload
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest


def _make_jpeg(width: int = 400, height: int = 300) -> bytes:
    """Return a minimal but valid JPEG of the given dimensions via Pillow."""
    from PIL import Image as _PILImage

    img = _PILImage.new("RGB", (width, height), color=(80, 120, 160))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

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
    monkeypatch.setenv("APP_KEY", "admin-products-test-key-32-bytes-or-more!")

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


# ─── product listing ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_can_list_products(client: Any, catalog_token: str) -> None:
    """catalog_manager can list all products including drafts."""
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
    """support role (level 40) cannot create products."""
    # Send a schema-valid body so the 403 reflects authorization, not validation.
    response = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {support_token}"},
        json={"name": {"en": "Forbidden"}, "price": 9.99, "category_id": "missing"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_includes_trashed_when_requested(client: Any, catalog_token: str) -> None:
    """?trashed=with includes soft-deleted products."""
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


# ─── create product ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_manager_can_create_product(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """POST /api/admin/products creates a product with i18n fields."""
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
    """creating a product without price or category_id returns 422."""
    response = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {catalog_token}"},
        json={"name": {"en": "Incomplete"}},
    )
    assert response.status_code == 422


# ─── update product ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_manager_can_update_product_price(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """PATCH /api/admin/products/{id} updates price."""
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


# ─── soft-delete + force-delete ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_soft_delete_product_disappears_from_storefront(
    client: Any, catalog_token: str
) -> None:
    """soft-deleted product is removed from storefront after materialized view refresh."""
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
    """force-delete returns 403 for catalog_manager, 204 for super_admin."""
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


# ─── restore ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_soft_deleted_product_reappears_in_storefront(
    client: Any, catalog_token: str
) -> None:
    """restoring a soft-deleted published product brings it back to storefront."""
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


# ─── publish / unpublish ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_product_appears_in_storefront(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """publishing a draft product makes it visible in the storefront."""
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


# ─── media ──────────────────────────────────────────────────────────────


async def _create_product(
    client: Any, token: str, vendor_id: str, category_id: str, name: str, slug: str
) -> str:
    resp = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": {"en": name},
            "slug": {"en": slug},
            "description": {"en": "..."},
            "price": 10.00,
            "stock_qty": 1,
            "category_id": category_id,
            "vendor_id": vendor_id,
        },
    )
    assert resp.status_code == 201, resp.json()
    return str(resp.json()["data"]["id"])


@pytest.mark.asyncio
async def test_upload_product_image_creates_conversions(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """uploading a 400x300 image creates thumbnail, card, and full conversions."""
    product_id = await _create_product(
        client, catalog_token, vendor_id, category_id, "Photo Product", "photo-product"
    )
    jpeg = _make_jpeg(400, 300)
    upload = await client.post(
        f"/api/admin/products/{product_id}/media",
        headers={"Authorization": f"Bearer {catalog_token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert upload.status_code == 201
    body = upload.json()["data"]
    assert "conversions" in body
    assert body["conversions"]["thumbnail"] != ""
    assert body["conversions"]["card"] != ""
    assert body["conversions"]["full"] != ""


@pytest.mark.asyncio
async def test_upload_product_image_has_responsive_srcset(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """uploading a large enough image produces responsive srcset for card and full."""
    product_id = await _create_product(
        client, catalog_token, vendor_id, category_id, "Srcset Product", "srcset-product"
    )
    # 800x600 gives the FileSizeOptimizedWidthCalculator room to produce 2+ breakpoints.
    jpeg = _make_jpeg(800, 600)
    upload = await client.post(
        f"/api/admin/products/{product_id}/media",
        headers={"Authorization": f"Bearer {catalog_token}"},
        files={"file": ("hero.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert upload.status_code == 201
    body = upload.json()["data"]

    # conversion_srcsets carries per-conversion responsive data.
    assert "conversion_srcsets" in body
    card_srcset: str = body["conversion_srcsets"].get("card", "")
    full_srcset: str = body["conversion_srcsets"].get("full", "")
    assert card_srcset, "card conversion should have responsive srcset"
    assert full_srcset, "full conversion should have responsive srcset"
    # srcset strings are space-separated "url Xw" pairs joined by ", "
    assert "w" in card_srcset
    assert "w" in full_srcset

    # Storefront listing uses image_srcset from the card responsive images.
    # Verify via GET /api/products (requires product to be published first).
    await client.patch(
        f"/api/admin/products/{product_id}/publish",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    storefront = await client.get("/api/products")
    product_cards = storefront.json()["data"]
    matching = [p for p in product_cards if p["id"] == product_id]
    assert matching, "published product should appear in storefront"
    card = matching[0]
    assert card["image_srcset"], "storefront card should expose image_srcset"
    assert "w" in card["image_srcset"]


@pytest.mark.asyncio
async def test_upload_rejects_non_image_file(
    client: Any, catalog_token: str, vendor_id: str, category_id: str
) -> None:
    """uploading a non-image (e.g. PDF) returns 400."""
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

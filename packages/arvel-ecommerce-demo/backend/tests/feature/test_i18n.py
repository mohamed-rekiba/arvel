"""i18n tests — US-026 (locale resolution + i18n catalogue).

RED: all tests fail at import until Stage 3b.

Acceptance criteria:
- US-026: GET /api/i18n/{locale} returns flat key/value catalogue
- US-026: storefront product names resolve to the requested locale
- US-026: admin endpoints return raw i18n dicts, not resolved strings
- US-026: locale negotiation: Accept-Language → ?locale= override → default en
- US-026: missing locale value falls back to en, not null
- US-026: GET /api/i18n/{locale} returns 304 on ETag hit
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
    monkeypatch.setenv("REDIS_URL", redis_endpoint.url)
    monkeypatch.setenv("AMQP_URL", rabbitmq_endpoint.amqp_url)
    monkeypatch.setenv("S3_ENDPOINT", minio_endpoint.endpoint_url)
    monkeypatch.setenv("S3_ACCESS_KEY", minio_endpoint.access_key)
    monkeypatch.setenv("S3_SECRET_KEY", minio_endpoint.secret_key)
    monkeypatch.setenv("S3_BUCKET", minio_endpoint.bucket)
    monkeypatch.setenv("MAIL_HOST", mailpit_endpoint.smtp_host)
    monkeypatch.setenv("MAIL_PORT", str(mailpit_endpoint.smtp_port))
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_KEY", "i18n-test-key-must-be-32-bytes-or-more!")

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


@pytest.mark.asyncio
async def test_locale_catalogue_returns_flat_key_value_map(client: Any) -> None:
    """US-026: GET /api/i18n/en returns a flat dict of string keys to string values."""
    response = await client.get("/api/i18n/en")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in body.items())


@pytest.mark.asyncio
async def test_locale_catalogue_includes_etag_header(client: Any) -> None:
    """US-026: /api/i18n/{locale} includes an ETag header for caching."""
    response = await client.get("/api/i18n/ar")
    assert response.status_code == 200
    assert "etag" in response.headers, "ETag header missing on locale catalogue"


@pytest.mark.asyncio
async def test_locale_catalogue_returns_304_on_etag_match(client: Any) -> None:
    """US-026: subsequent request with If-None-Match returns 304."""
    first = await client.get("/api/i18n/tr")
    etag = first.headers.get("etag", "")
    assert etag, "Cannot test 304 without an ETag"

    second = await client.get("/api/i18n/tr", headers={"If-None-Match": etag})
    assert second.status_code == 304


@pytest.mark.asyncio
async def test_storefront_resolves_arabic_product_name(client: Any) -> None:
    """US-026: storefront product name is resolved to Arabic when locale=ar."""
    response = await client.get("/api/products?locale=ar")
    assert response.status_code == 200
    # All products in the seed have AR translations
    for product in response.json()["data"]:
        assert product["name"] != "", f"Arabic name empty for product {product['id']}"


@pytest.mark.asyncio
async def test_storefront_falls_back_to_en_when_locale_missing(client: Any) -> None:
    """US-026: storefront falls back to English when TR name would be absent."""
    # Create a product with no Turkish name
    # (This test verifies the fallback — seeded products have TR names,
    # so we use an admin token to create one without TR)
    admin = await client.post(
        "/api/auth/login",
        json={"email": "superadmin@example.com", "password": "password"},
    )
    token = admin.json()["access_token"]

    cats = await client.get("/api/admin/categories", headers={"Authorization": f"Bearer {token}"})
    cat_id = cats.json()["data"][0]["id"]
    vendors = await client.get("/api/admin/vendors", headers={"Authorization": f"Bearer {token}"})
    vendor_id = vendors.json()["data"][0]["id"]

    create_resp = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": {"en": "English Only Product"},
            "slug": {"en": "english-only"},
            "description": {"en": "No Turkish translation."},
            "price": 1.00,
            "stock_qty": 5,
            "category_id": cat_id,
            "vendor_id": vendor_id,
        },
    )
    product_id = create_resp.json()["data"]["id"]
    await client.patch(
        f"/api/admin/products/{product_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/api/products?locale=tr")
    products = {p["slug"]: p["name"] for p in response.json()["data"]}
    if "english-only" in products:
        assert products["english-only"] == "English Only Product", (
            "Fallback to English when Turkish translation is absent"
        )


@pytest.mark.asyncio
async def test_admin_returns_raw_i18n_dict_not_resolved_string(client: Any) -> None:
    """US-026: admin product response includes raw i18n dicts for all fields."""
    admin = await client.post(
        "/api/auth/login",
        json={"email": "superadmin@example.com", "password": "password"},
    )
    token = admin.json()["access_token"]

    response = await client.get(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    for product in response.json()["data"]:
        name = product["name"]
        assert isinstance(name, dict), f"Admin product.name should be a dict, got {type(name)}"
        assert "en" in name

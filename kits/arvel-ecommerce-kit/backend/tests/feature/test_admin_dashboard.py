"""Admin dashboard stats endpoint.

Coverage:
- orders.view is required (support can read, customer cannot)
- aggregates are all-time, not capped by a page of results
- the 7-day revenue series always has exactly 7 day buckets
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
    monkeypatch.setenv("APP_KEY", "dashboard-test-key-must-be-32-bytes-or-more!")

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
async def support_token(client: Any) -> str:
    return await _login(client, "support@example.com", "password")


@pytest.fixture
async def customer_token(client: Any) -> str:
    return await _login(client, "customer@example.com", "password")


@pytest.fixture
async def super_admin_token(client: Any) -> str:
    return await _login(client, "superadmin@example.com", "password")


@pytest.mark.asyncio
async def test_stats_requires_orders_view(client: Any, customer_token: str) -> None:
    """A customer (no orders.view) is forbidden."""
    response = await client.get(
        "/api/admin/orders/stats", headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_stats_shape_and_seven_day_series(client: Any, support_token: str) -> None:
    """support can read; the payload is well-formed with a 7-point revenue series."""
    response = await client.get(
        "/api/admin/orders/stats", headers={"Authorization": f"Bearer {support_token}"}
    )
    assert response.status_code == 200
    body = response.json()

    for key in (
        "total_revenue",
        "total_orders",
        "unique_customers",
        "avg_order_value",
        "status_counts",
        "revenue_last_7_days",
    ):
        assert key in body

    assert body["total_orders"] >= 0
    assert isinstance(body["status_counts"], dict)
    series = body["revenue_last_7_days"]
    assert len(series) == 7
    # ascending, distinct calendar days
    dates = [p["date"] for p in series]
    assert dates == sorted(dates)
    assert len(set(dates)) == 7
    # status counts never exceed the all-time order total
    assert sum(body["status_counts"].values()) <= body["total_orders"]


@pytest.mark.asyncio
async def test_cancelled_orders_excluded_from_revenue(
    client: Any, super_admin_token: str, customer_token: str
) -> None:
    """Cancelling an order rolls its total back out of dashboard revenue."""
    sa = {"Authorization": f"Bearer {super_admin_token}"}
    cust = {"Authorization": f"Bearer {customer_token}"}

    baseline = (await client.get("/api/admin/orders/stats", headers=sa)).json()["total_revenue"]

    listing = await client.get("/api/products")
    product_id = listing.json()["data"][0]["id"]
    await client.post(
        "/api/cart/items", headers=cust, json={"product_id": product_id, "quantity": 1}
    )
    checkout = await client.post(
        "/api/checkout",
        headers=cust,
        json={
            "shipping_address": {"name": "Pat", "street": "1 St", "city": "City", "country": "US"}
        },
    )
    assert checkout.status_code == 201
    order_id = checkout.json()["data"]["id"]

    with_order = (await client.get("/api/admin/orders/stats", headers=sa)).json()["total_revenue"]
    assert with_order > baseline

    cancel = await client.patch(
        f"/api/admin/orders/{order_id}/status", headers=sa, json={"status": "cancelled"}
    )
    assert cancel.status_code == 200

    after_cancel = (await client.get("/api/admin/orders/stats", headers=sa)).json()["total_revenue"]
    assert after_cancel == baseline


async def _login(client: Any, email: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, f"Login failed: {response.json()}"
    return str(response.json()["access_token"])

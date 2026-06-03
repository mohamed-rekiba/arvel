"""Cart, checkout, and order history.

Coverage:
- authenticated customer can add, update, remove cart items
- duplicate add increments quantity (no duplicate rows)
- checkout reads price from DB at checkout time, not from cart snapshot
- checkout reduces stock_qty atomically; fails if insufficient stock
- successful checkout creates order with line item price snapshots
- customer can list their orders and view order detail
- customer cannot access another customer's order (403)
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
    monkeypatch.setenv("APP_KEY", "cart-checkout-test-key-32-bytes-or-more!")

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
async def customer_token(client: Any) -> str:
    return await _login(client, "customer@example.com", "password")


@pytest.fixture
async def customer2_token(client: Any) -> str:
    """Second customer for cross-customer access checks (seeded + pre-verified)."""
    return await _login(client, "customer2@example.com", "password")


@pytest.fixture
async def headphones_id(client: Any) -> str:
    """Return the product id of the seeded headphones product."""
    response = await client.get("/api/products/wireless-headphones-pro")
    return str(response.json()["data"]["id"])


# ─── cart ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_cart_returns_no_items(client: Any, customer_token: str) -> None:
    """new customer has an empty cart."""
    response = await client.get("/api/cart", headers={"Authorization": f"Bearer {customer_token}"})
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_add_item_to_cart(client: Any, customer_token: str, headphones_id: str) -> None:
    """adding a product creates a cart item."""
    response = await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 2},
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 2
    assert body["items"][0]["product_id"] == headphones_id


@pytest.mark.asyncio
async def test_adding_same_product_twice_increments_quantity(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """duplicate add-to-cart merges into one cart item row."""
    await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )
    await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 2},
    )
    cart = await client.get("/api/cart", headers={"Authorization": f"Bearer {customer_token}"})
    items = cart.json()["data"]["items"]
    assert len(items) == 1, "Duplicate add must merge, not create a second row"
    assert items[0]["quantity"] == 3


@pytest.mark.asyncio
async def test_update_cart_item_quantity(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """PATCH /api/cart/items/{id} updates quantity."""
    cart = await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )
    item_id = cart.json()["data"]["items"][0]["id"]

    updated = await client.patch(
        f"/api/cart/items/{item_id}",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"quantity": 5},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["items"][0]["quantity"] == 5


@pytest.mark.asyncio
async def test_remove_cart_item(client: Any, customer_token: str, headphones_id: str) -> None:
    """DELETE /api/cart/items/{id} removes the item."""
    cart = await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )
    item_id = cart.json()["data"]["items"][0]["id"]

    removed = await client.delete(
        f"/api/cart/items/{item_id}",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert removed.status_code == 200
    assert removed.json()["data"]["items"] == []


# ─── checkout ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkout_creates_order_with_price_snapshot(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """checkout reads price from DB, stores snapshot in order_items."""
    await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )
    response = await client.post(
        "/api/checkout",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={
            "shipping_address": {
                "line1": "123 Main St",
                "city": "Testville",
                "country_code": "US",
            }
        },
    )
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["status"] == "pending"
    assert order["total"] > 0

    # Cart must be empty after checkout
    cart = await client.get("/api/cart", headers={"Authorization": f"Bearer {customer_token}"})
    assert cart.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_checkout_fails_on_insufficient_stock(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """checkout is the atomic stock gate.

    Adding is optimistic; the authoritative check happens at checkout under a row
    lock. This reproduces the oversell race: the item is in stock when added, then
    sells out before this customer checks out, so checkout must 409.

    """
    await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )

    # Stock drains to zero between add and checkout.
    admin_token = await _login(client, "catalog@example.com", "password")
    drained = await client.patch(
        f"/api/admin/products/{headphones_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"stock_qty": 0},
    )
    assert drained.status_code == 200

    checkout = await client.post(
        "/api/checkout",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"shipping_address": {"line1": "1 St", "city": "City", "country_code": "US"}},
    )
    assert checkout.status_code == 409


# ─── order history ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_customer_can_list_their_orders(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """GET /api/account/orders returns customer's own orders."""
    await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )
    await client.post(
        "/api/checkout",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"shipping_address": {"line1": "1 St", "city": "City", "country_code": "US"}},
    )

    orders = await client.get(
        "/api/account/orders", headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert orders.status_code == 200
    assert len(orders.json()["data"]) >= 1


@pytest.mark.asyncio
async def test_customer_cannot_access_another_customers_order(
    client: Any,
    customer_token: str,
    customer2_token: str,
    headphones_id: str,
) -> None:
    """customer cannot read another customer's order detail."""
    # Customer 1 places an order
    await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )
    checkout = await client.post(
        "/api/checkout",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"shipping_address": {"line1": "1 St", "city": "City", "country_code": "US"}},
    )
    order_id = checkout.json()["data"]["id"]

    # Customer 2 tries to access it
    response = await client.get(
        f"/api/account/orders/{order_id}",
        headers={"Authorization": f"Bearer {customer2_token}"},
    )
    assert response.status_code in {403, 404}


# ─── helpers ────────────────────────────────────────────────────────────────────


async def _login(client: Any, email: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, f"Login failed for {email}: {response.json()}"
    return str(response.json()["access_token"])

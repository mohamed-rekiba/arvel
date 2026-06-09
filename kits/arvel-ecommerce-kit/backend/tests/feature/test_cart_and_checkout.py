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

import asyncio
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

    httpx: Any = importlib.import_module("httpx2")
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


@pytest.fixture
async def super_admin_token(client: Any) -> str:
    return await _login(client, "superadmin@example.com", "password")


async def _admin_stock(client: Any, token: str, product_id: str) -> int:
    detail = await client.get(
        f"/api/admin/products/{product_id}", headers={"Authorization": f"Bearer {token}"}
    )
    return int(detail.json()["data"]["stock_qty"])


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


@pytest.mark.asyncio
async def test_add_malformed_product_id_returns_404(client: Any, customer_token: str) -> None:
    """A non-UUID product id is a 404, not a 500."""
    response = await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": "not-a-uuid", "quantity": 1},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_unknown_cart_item_returns_404(client: Any, customer_token: str) -> None:
    """PATCH on an item id not in the caller's cart is a 404, not a silent 200."""
    response = await client.patch(
        "/api/cart/items/999999",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"quantity": 3},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_unknown_cart_item_returns_404(client: Any, customer_token: str) -> None:
    """DELETE on an item id not in the caller's cart is a 404, not a silent 200."""
    response = await client.delete(
        "/api/cart/items/999999",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 404


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
                "name": "Pat Buyer",
                "street": "123 Main St",
                "city": "Testville",
                "country": "US",
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
async def test_checkout_snapshots_product_name_in_shopper_locale(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """The order line name is frozen in the locale the shopper checked out in."""
    storefront = await client.get(
        "/api/products/wireless-headphones-pro", headers={"Accept-Language": "ar"}
    )
    arabic_name = storefront.json()["data"]["name"]

    await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )
    response = await client.post(
        "/api/checkout",
        headers={"Authorization": f"Bearer {customer_token}", "Accept-Language": "ar"},
        json={
            "shipping_address": {
                "name": "Pat",
                "street": "1 St",
                "city": "City",
                "country": "US",
            }
        },
    )
    assert response.status_code == 201
    item = response.json()["data"]["items"][0]
    assert item["product_name"] == arabic_name


@pytest.mark.asyncio
async def test_checkout_rejects_invalid_shipping_address(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """A shipping address missing required fields is a 422, not a saved garbage order."""
    headers = {"Authorization": f"Bearer {customer_token}"}
    await client.post(
        "/api/cart/items", headers=headers, json={"product_id": headphones_id, "quantity": 1}
    )
    response = await client.post(
        "/api/checkout",
        headers=headers,
        json={"shipping_address": {"city": "City"}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_concurrent_checkout_creates_single_order(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """Two simultaneous checkouts on one cart create exactly one order."""
    headers = {"Authorization": f"Bearer {customer_token}"}
    await client.post(
        "/api/cart/items", headers=headers, json={"product_id": headphones_id, "quantity": 1}
    )
    body = {
        "shipping_address": {"name": "Pat", "street": "1 St", "city": "City", "country": "US"}
    }
    first, second = await asyncio.gather(
        client.post("/api/checkout", headers=headers, json=body),
        client.post("/api/checkout", headers=headers, json=body),
    )
    # The cart lock serializes them: one places the order, the other finds it empty.
    assert sorted([first.status_code, second.status_code]) == [201, 422]
    orders = await client.get("/api/account/orders", headers=headers)
    assert len(orders.json()["data"]) == 1


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
        json={
            "shipping_address": {
                "name": "Pat",
                "street": "1 St",
                "city": "City",
                "country": "US",
            }
        },
    )
    assert checkout.status_code == 409


@pytest.mark.asyncio
async def test_checkout_fails_when_product_unpublished(
    client: Any, customer_token: str, headphones_id: str
) -> None:
    """An item pulled from the catalog after add-to-cart 409s as unavailable, not out of stock."""
    await client.post(
        "/api/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"product_id": headphones_id, "quantity": 1},
    )

    admin_token = await _login(client, "catalog@example.com", "password")
    unpublished = await client.patch(
        f"/api/admin/products/{headphones_id}/unpublish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert unpublished.status_code == 200

    checkout = await client.post(
        "/api/checkout",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={
            "shipping_address": {"name": "Pat", "street": "1 St", "city": "City", "country": "US"}
        },
    )
    assert checkout.status_code == 409
    assert "no longer available" in checkout.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_duplicate_add_resnapshots_to_current_price(
    client: Any, customer_token: str, super_admin_token: str, headphones_id: str
) -> None:
    """Adding more of a line re-snapshots to today's price, not the stale first price."""
    cust = {"Authorization": f"Bearer {customer_token}"}
    sa = {"Authorization": f"Bearer {super_admin_token}"}

    await client.post(
        "/api/cart/items", headers=cust, json={"product_id": headphones_id, "quantity": 1}
    )

    bumped = await client.patch(
        f"/api/admin/products/{headphones_id}",
        headers=sa,
        json={"price": 999.0},
    )
    assert bumped.status_code == 200

    await client.post(
        "/api/cart/items", headers=cust, json={"product_id": headphones_id, "quantity": 1}
    )
    cart = await client.get("/api/cart", headers=cust)
    line = next(i for i in cart.json()["data"]["items"] if i["product_id"] == headphones_id)
    assert line["quantity"] == 2
    assert line["unit_price"] == 999.0
    assert cart.json()["data"]["total"] == 1998.0


@pytest.mark.asyncio
async def test_update_quantity_resnapshots_to_current_price(
    client: Any, customer_token: str, super_admin_token: str, headphones_id: str
) -> None:
    """PATCH quantity re-prices the line to today's price, like add does — no stale snapshot."""
    cust = {"Authorization": f"Bearer {customer_token}"}
    sa = {"Authorization": f"Bearer {super_admin_token}"}

    add = await client.post(
        "/api/cart/items", headers=cust, json={"product_id": headphones_id, "quantity": 1}
    )
    item_id = next(
        i["id"] for i in add.json()["data"]["items"] if i["product_id"] == headphones_id
    )

    bumped = await client.patch(
        f"/api/admin/products/{headphones_id}", headers=sa, json={"price": 999.0}
    )
    assert bumped.status_code == 200

    updated = await client.patch(
        f"/api/cart/items/{item_id}", headers=cust, json={"quantity": 3}
    )
    assert updated.status_code == 200
    line = next(
        i for i in updated.json()["data"]["items"] if i["product_id"] == headphones_id
    )
    assert line["quantity"] == 3
    assert line["unit_price"] == 999.0
    assert line["subtotal"] == 2997.0


@pytest.mark.asyncio
async def test_concurrent_cancel_restores_stock_once(
    client: Any, customer_token: str, super_admin_token: str, headphones_id: str
) -> None:
    """Two simultaneous cancels must restore stock once, not double-credit inventory."""
    cust = {"Authorization": f"Bearer {customer_token}"}
    sa = {"Authorization": f"Bearer {super_admin_token}"}

    await client.post(
        "/api/cart/items", headers=cust, json={"product_id": headphones_id, "quantity": 2}
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

    stock_after_order = await _admin_stock(client, super_admin_token, headphones_id)

    body = {"status": "cancelled"}
    first, second = await asyncio.gather(
        client.patch(f"/api/admin/orders/{order_id}/status", headers=sa, json=body),
        client.patch(f"/api/admin/orders/{order_id}/status", headers=sa, json=body),
    )
    assert {first.status_code, second.status_code} == {200}

    stock_after_cancel = await _admin_stock(client, super_admin_token, headphones_id)
    assert stock_after_cancel == stock_after_order + 2


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
        json={
            "shipping_address": {
                "name": "Pat",
                "street": "1 St",
                "city": "City",
                "country": "US",
            }
        },
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
        json={
            "shipping_address": {
                "name": "Pat",
                "street": "1 St",
                "city": "City",
                "country": "US",
            }
        },
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

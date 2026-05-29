"""RBAC tests — US-005 (role enforcement) + US-024-025 (user management).

RED: all tests fail at import until Stage 3b.

Acceptance criteria:
- US-005: permission check fires at dependency level before handler
- US-005: support can read products but cannot create them
- US-005: catalog_manager can publish but cannot manage users
- US-024: users.manage permission required to list/soft-delete users
- US-025: roles.manage permission required to assign/revoke roles
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
    monkeypatch.setenv("APP_KEY", "rbac-test-key-must-be-32-bytes-or-more!")

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
async def super_admin_token(client: Any) -> str:
    return await _login(client, "superadmin@example.com", "password")


@pytest.fixture
async def catalog_token(client: Any) -> str:
    return await _login(client, "catalog@example.com", "password")


@pytest.fixture
async def support_token(client: Any) -> str:
    return await _login(client, "support@example.com", "password")


@pytest.fixture
async def customer_token(client: Any) -> str:
    return await _login(client, "customer@example.com", "password")


# ─── US-005: permission enforcement ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthenticated_request_to_admin_returns_401(client: Any) -> None:
    """US-005: admin endpoints reject unauthenticated requests with 401."""
    response = await client.get("/api/admin/products")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_customer_cannot_access_admin_products(client: Any, customer_token: str) -> None:
    """US-005: customer role has no products.view permission → 403."""
    response = await client.get(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_support_can_view_but_not_create_products(client: Any, support_token: str) -> None:
    """US-005: support (level 40) has products.view but not products.create."""
    view = await client.get(
        "/api/admin/products", headers={"Authorization": f"Bearer {support_token}"}
    )
    assert view.status_code == 200

    create = await client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {support_token}"},
        json={
            "name": {"en": "X"},
            "price": 1,
            "category_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert create.status_code == 403


@pytest.mark.asyncio
async def test_catalog_manager_cannot_manage_users(client: Any, catalog_token: str) -> None:
    """US-005: catalog_manager lacks users.manage → 403 on /api/admin/users."""
    response = await client.get(
        "/api/admin/users", headers={"Authorization": f"Bearer {catalog_token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_catalog_manager_cannot_force_delete(
    client: Any, catalog_token: str, super_admin_token: str
) -> None:
    """US-005: force-delete requires super_admin level (100); catalog (60) gets 403."""
    products = await client.get(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    product_id = products.json()["data"][0]["id"]

    await client.delete(
        f"/api/admin/products/{product_id}",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    response = await client.delete(
        f"/api/admin/products/{product_id}/force",
        headers={"Authorization": f"Bearer {catalog_token}"},
    )
    assert response.status_code == 403


# ─── US-024: user management ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_super_admin_can_list_users(client: Any, super_admin_token: str) -> None:
    """US-024: users.manage permission required to list users."""
    response = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


@pytest.mark.asyncio
async def test_super_admin_can_soft_delete_user(client: Any, super_admin_token: str) -> None:
    """US-024: soft-deleting a user sets their deleted_at."""
    users = await client.get(
        "/api/admin/users?trashed=without",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    # Don't delete the super admin themselves — pick another user
    other_users = [u for u in users.json()["data"] if u["email"] != "superadmin@example.com"]
    assert other_users, "No non-admin users to test soft-delete against"
    user_id = other_users[0]["id"]

    delete = await client.delete(
        f"/api/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert delete.status_code == 204


# ─── US-025: role assignment ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_super_admin_can_assign_role_to_user(client: Any, super_admin_token: str) -> None:
    """US-025: POST /api/admin/users/{id}/roles assigns a role."""
    users = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    customer = next(u for u in users.json()["data"] if u["email"] == "customer@example.com")
    user_id = customer["id"]

    response = await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={"role": "support"},
    )
    assert response.status_code == 200
    roles = {r["slug"] for r in response.json()["data"]["roles"]}
    assert "support" in roles


@pytest.mark.asyncio
async def test_super_admin_can_grant_direct_permission(client: Any, super_admin_token: str) -> None:
    """US-025: POST /api/admin/users/{id}/permissions grants a direct permission."""
    users = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    customer = next(u for u in users.json()["data"] if u["email"] == "customer@example.com")
    user_id = customer["id"]

    response = await client.post(
        f"/api/admin/users/{user_id}/permissions",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={"permission": "orders.view"},
    )
    assert response.status_code == 200
    direct_perms = {p["slug"] for p in response.json()["data"]["direct_permissions"]}
    assert "orders.view" in direct_perms


# ─── helpers ────────────────────────────────────────────────────────────────────


async def _login(client: Any, email: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, f"Login failed for {email}: {response.json()}"
    return str(response.json()["access_token"])

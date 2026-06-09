"""RBAC enforcement and admin user/role management.

Coverage:
- permission check fires at dependency level before handler
- support can read products but cannot create them
- catalog_manager can publish but cannot manage users
- users.manage permission required to list/soft-delete users
- roles.manage permission required to assign/revoke roles
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
    monkeypatch.setenv("APP_KEY", "rbac-test-key-must-be-32-bytes-or-more!")

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


# ─── permission enforcement ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthenticated_request_to_admin_returns_401(client: Any) -> None:
    """admin endpoints reject unauthenticated requests with 401."""
    response = await client.get("/api/admin/products")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_exposes_role_level(
    client: Any, super_admin_token: str, catalog_token: str
) -> None:
    """/me reports the caller's highest role level so the UI can gate level-restricted actions."""
    sa = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {super_admin_token}"})
    assert sa.status_code == 200
    assert sa.json()["role_level"] == 100

    catalog = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {catalog_token}"})
    assert catalog.json()["role_level"] < 100


@pytest.mark.asyncio
async def test_user_detail_shows_effective_permissions(client: Any, super_admin_token: str) -> None:
    """The detail view resolves the effective permission set, not just direct grants."""
    headers = {"Authorization": f"Bearer {super_admin_token}"}
    listing = await client.get("/api/admin/users", headers=headers)
    sa = next(u for u in listing.json()["data"] if "super_admin" in u["roles"])

    detail = await client.get(f"/api/admin/users/{sa['id']}", headers=headers)
    data = detail.json()["data"]
    # super_admin's perms come from the role, not direct grants.
    assert "users.manage" in data["permissions"]
    assert len(data["permissions"]) > len(data["direct_permissions"])


@pytest.mark.asyncio
async def test_customer_cannot_access_admin_products(client: Any, customer_token: str) -> None:
    """customer role has no products.view permission → 403."""
    response = await client.get(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_support_can_view_but_not_create_products(client: Any, support_token: str) -> None:
    """support (level 40) has products.view but not products.create."""
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
    """catalog_manager lacks users.manage → 403 on /api/admin/users."""
    response = await client.get(
        "/api/admin/users", headers={"Authorization": f"Bearer {catalog_token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_catalog_manager_cannot_force_delete(
    client: Any, catalog_token: str, super_admin_token: str
) -> None:
    """force-delete requires super_admin level (100); catalog (60) gets 403."""
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


# ─── user management ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_super_admin_can_list_users(client: Any, super_admin_token: str) -> None:
    """users.manage permission required to list users."""
    response = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


@pytest.mark.asyncio
async def test_super_admin_can_soft_delete_user(client: Any, super_admin_token: str) -> None:
    """soft-deleting a user sets their deleted_at."""
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


@pytest.mark.asyncio
async def test_admin_cannot_delete_their_own_account(client: Any, super_admin_token: str) -> None:
    """An admin can't soft- or hard-delete themselves — losing your own access is a footgun."""
    sa = {"Authorization": f"Bearer {super_admin_token}"}
    listing = await client.get("/api/admin/users?search=superadmin@example.com", headers=sa)
    me = next(u for u in listing.json()["data"] if u["email"] == "superadmin@example.com")

    soft = await client.delete(f"/api/admin/users/{me['id']}", headers=sa)
    assert soft.status_code == 403
    hard = await client.delete(f"/api/admin/users/{me['id']}/force", headers=sa)
    assert hard.status_code == 403


# ─── role assignment ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_super_admin_can_assign_role_to_user(client: Any, super_admin_token: str) -> None:
    """POST /api/admin/users/{id}/roles assigns a role."""
    users = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    customer = next(u for u in users.json()["data"] if u["email"] == "customer@example.com")
    user_id = customer["id"]

    response = await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={"role": "support_agent"},
    )
    assert response.status_code == 200
    roles = set(response.json()["data"]["roles"])
    assert "support_agent" in roles


@pytest.mark.asyncio
async def test_super_admin_can_grant_direct_permission(client: Any, super_admin_token: str) -> None:
    """POST /api/admin/users/{id}/permissions grants a direct permission."""
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
    direct_perms = set(response.json()["data"]["direct_permissions"])
    assert "orders.view" in direct_perms


@pytest.mark.asyncio
async def test_translations_requires_both_product_and_category_view(
    client: Any, super_admin_token: str, customer_token: str
) -> None:
    """Translations expose product + category fields, so categories.view alone isn't enough."""
    sa = {"Authorization": f"Bearer {super_admin_token}"}
    users = await client.get("/api/admin/users", headers=sa)
    customer = next(u for u in users.json()["data"] if u["email"] == "customer@example.com")

    # Grant only categories.view — deliberately not products.view.
    grant = await client.post(
        f"/api/admin/users/{customer['id']}/permissions",
        headers=sa,
        json={"permission": "categories.view"},
    )
    assert grant.status_code == 200

    resp = await client.get(
        "/api/admin/translations", headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert resp.status_code == 403, "categories.view alone must not expose product translations"


@pytest.mark.asyncio
async def test_self_registration_assigns_customer_role(client: Any, super_admin_token: str) -> None:
    """A self-registered user lands inside RBAC with the baseline customer role."""
    email = "newbie@example.com"
    reg = await client.post(
        "/api/auth/register",
        json={
            "name": "New Bie",
            "email": email,
            "password": "password123",
            "password_confirmation": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.json()

    sa = {"Authorization": f"Bearer {super_admin_token}"}
    listing = await client.get(f"/api/admin/users?search={email}", headers=sa)
    user = next(u for u in listing.json()["data"] if u["email"] == email)
    assert "customer" in user["roles"]


# ─── helpers ────────────────────────────────────────────────────────────────────


async def _login(client: Any, email: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, f"Login failed for {email}: {response.json()}"
    return str(response.json()["access_token"])

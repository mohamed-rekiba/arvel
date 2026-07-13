"""H1 — domain/subdomain routing: a route's ``domain`` pattern is matched against the request
``Host`` header at dispatch (not pushed into Litestar's own router, which can't hold two handlers
on the same method+path — arvel already owns dispatch/binding, so the host check lives there
too). A ``{param}`` domain segment is captured into the handler params exactly like a path param."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router


async def _admin(request: Any) -> dict[str, str]:
    return {"area": "admin"}


async def _shop(request: Any) -> dict[str, str]:
    return {"area": "shop"}


async def _tenant(request: Any, account: str) -> dict[str, str]:
    return {"account": account}


def _client(router: Router) -> TestClient[Any]:
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_two_routes_same_path_dispatch_by_host() -> None:
    router = Router()
    with router.group(domain="admin.example.com"):
        router.get("/dashboard", _admin)
    with router.group(domain="shop.example.com"):
        router.get("/dashboard", _shop)
    with _client(router) as client:
        assert client.get("/dashboard", headers={"host": "admin.example.com"}).json() == {
            "area": "admin"
        }
        assert client.get("/dashboard", headers={"host": "shop.example.com"}).json() == {
            "area": "shop"
        }


def test_non_matching_host_is_404_not_a_mis_bind() -> None:
    router = Router()
    with router.group(domain="admin.example.com"):
        router.get("/dashboard", _admin)
    with _client(router) as client:
        response = client.get("/dashboard", headers={"host": "evil.example.com"})
        assert response.status_code == 404


def test_domain_param_is_captured_and_injected() -> None:
    router = Router()
    with router.group(domain="{account}.example.com"):
        router.get("/whoami", _tenant)
    with _client(router) as client:
        response = client.get("/whoami", headers={"host": "acme.example.com"})
        assert response.json() == {"account": "acme"}


def test_route_with_no_domain_matches_any_host() -> None:
    router = Router()
    router.get("/ping", lambda request: {"pong": True})
    with _client(router) as client:
        assert client.get("/ping", headers={"host": "anything.example.com"}).json() == {
            "pong": True
        }
        assert client.get("/ping", headers={"host": "other.example.com"}).json() == {"pong": True}


def test_group_domain_applies_to_routes_in_block_and_restores_on_exit() -> None:
    router = Router()
    with router.group(domain="{account}.example.com"):
        router.get("/inside", _tenant, name="inside")
    router.get("/outside", lambda request: {"ok": True}, name="outside")
    assert router.routes()[0].domain == "{account}.example.com"
    assert router.routes()[1].domain is None


def test_duplicate_domainless_route_is_a_loud_boot_error() -> None:
    import pytest

    router = Router()
    router.get("/dup", _admin)
    router.get("/dup", _shop)  # same method+path, neither domained → accidental shadow
    with pytest.raises(ValueError, match="duplicate route"):
        _client(router)


def test_mixed_case_host_matches_a_domain_route() -> None:
    router = Router()
    with router.group(domain="{account}.example.com"):
        router.get("/dashboard", _tenant)
    with _client(router) as client:
        assert client.get("/dashboard", headers={"host": "Acme.Example.COM"}).json() == {
            "account": "Acme"
        }

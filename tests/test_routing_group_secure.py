"""DR-0052 — ``group(secure=...)`` seeds ``RouteDefinition.security``, the OpenAPI-docs
counterpart to ``group(middleware=...)``: composes on nesting, restores on exit, and a
route's own ``.secure()`` still extends it."""

from __future__ import annotations

from arvel.routing import Router


def test_route_in_secure_group_gets_the_scheme() -> None:
    router = Router()
    with router.group(secure=["bearer"]):
        router.get("/in", lambda request: None, name="in")
    assert router.routes()[0].security == ["bearer"]


def test_nested_secure_groups_compose() -> None:
    router = Router()
    with router.group(secure=["bearer"]), router.group(secure=["oidc"]):
        router.get("/inner", lambda request: None, name="inner")
    assert router.routes()[0].security == ["bearer", "oidc"]


def test_route_after_secure_group_is_restored_to_empty() -> None:
    router = Router()
    with router.group(secure=["bearer"]):
        router.get("/in", lambda request: None, name="in")
    router.get("/after", lambda request: None, name="after")
    assert router.routes()[1].security == []


def test_per_route_secure_extends_group_scheme_no_dedup() -> None:
    router = Router()
    with router.group(secure=["bearer"]):
        router.get("/in", lambda request: None, name="in").secure("oidc")
    assert router.routes()[0].security == ["bearer", "oidc"]

"""OpenAPI: document identity comes from typed OpenApiSettings (DR-0016); request/response schemas
and clean operationIds are generated from the handlers' arvel.Schema types."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from litestar.testing import TestClient

from arvel import Schema
from arvel.kernel import set_application
from arvel.kernel.application import Application
from arvel.kernel.config import Repository
from arvel.routing import Router


class CreateThing(Schema):
    name: str


class ThingOut(Schema):
    id: int
    name: str


async def store(request: Any, data: CreateThing) -> ThingOut:
    """Create a thing from the posted name."""
    return ThingOut(id=1, name=data.name)


async def health(request: Any) -> ThingOut:
    return ThingOut(id=0, name="ok")


@pytest.fixture
def client() -> Iterator[TestClient[Any]]:
    from arvel.http import HttpKernel

    app = Application()
    app.instance(
        "config",
        Repository(
            {
                "openapi": {
                    "title": "My API",
                    "version": "3.0.0",
                    "description": "d",
                    "path": "/docs",
                }
            }
        ),
    )
    set_application(app)
    router = Router()
    router.post("/things", store, name="things.store")
    router.get("/health", health, name="health")
    kernel = HttpKernel(app)
    router.apply_to(kernel)
    try:
        yield TestClient(kernel.build())
    finally:
        set_application(None)


def test_openapi_info_comes_from_typed_settings(client: TestClient[Any]) -> None:
    with client as c:
        s = c.get("/docs/openapi.json").json()  # path is configurable (OpenApiSettings.path)
    assert s["info"] == {"title": "My API", "version": "3.0.0", "description": "d"}


def test_request_and_response_schemas_are_generated(client: TestClient[Any]) -> None:
    with client as c:
        s = c.get("/docs/openapi.json").json()
    schemas = s["components"]["schemas"]
    assert "CreateThing" in schemas and "ThingOut" in schemas
    post = s["paths"]["/things"]["post"]
    assert post["operationId"] == "things.store"  # clean opId from the route name
    assert post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "CreateThing"
    )
    resp = post["responses"]["201"]["content"]["application/json"]["schema"]
    assert resp["$ref"].endswith("ThingOut")
    assert s["paths"]["/health"]["get"]["operationId"] == "health"
    # the synthetic route adapter must carry the original handler's __doc__, not go blank
    assert post["description"] == "Create a thing from the posted name."


def test_typed_body_is_parsed_and_passed_to_the_handler(client: TestClient[Any]) -> None:
    with client as c:
        r = c.post("/things", json={"name": "ada"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "name": "ada"}


# --- expanded config surface + auth/security ---


@contextmanager
def _serve(openapi: dict[str, Any], routes: Router) -> Iterator[TestClient[Any]]:
    from arvel.http import HttpKernel

    app = Application()
    app.instance("config", Repository({"openapi": openapi}))
    set_application(app)
    kernel = HttpKernel(app)
    routes.apply_to(kernel)
    try:
        with TestClient(kernel.build()) as c:
            yield c
    finally:
        set_application(None)


def test_full_config_surface_maps_to_the_document() -> None:
    router = Router()
    router.get("/health", health, name="health")
    cfg = {
        "title": "Blog",
        "summary": "A blog API",
        "terms_of_service": "https://blog.test/tos",
        "contact": {"name": "Team", "email": "t@blog.test"},
        "license": {"name": "MIT"},
        "servers": [{"url": "https://api.blog.test", "description": "prod"}],
        "tags": [{"name": "auth", "description": "Authentication"}],
        "external_docs": {"url": "https://docs.blog.test"},
    }
    with _serve(cfg, router) as c:
        s = c.get("/schema/openapi.json").json()
    assert s["info"]["summary"] == "A blog API"
    assert s["info"]["termsOfService"] == "https://blog.test/tos"
    assert s["info"]["contact"] == {"name": "Team", "email": "t@blog.test"}
    assert s["info"]["license"] == {"name": "MIT"}
    assert s["servers"] == [{"url": "https://api.blog.test", "description": "prod"}]
    assert s["tags"] == [{"name": "auth", "description": "Authentication"}]
    assert s["externalDocs"]["url"] == "https://docs.blog.test"


def test_ui_renderer_is_configurable() -> None:
    router = Router()
    router.get("/health", health, name="health")
    with _serve({"ui": "redoc", "path": "/api-docs"}, router) as c:
        assert c.get("/api-docs").status_code == 200  # docs UI served at the configured path


def test_bearer_security_scheme_and_per_route_secure() -> None:
    router = Router()
    router.get("/public", health, name="public")
    router.get("/private", health, name="private").secure("bearer")
    with _serve({"security": {"bearer": True}}, router) as c:
        s = c.get("/schema/openapi.json").json()
    scheme = s["components"]["securitySchemes"]["bearerAuth"]
    assert scheme["type"] == "http" and scheme["scheme"] == "bearer"
    assert s.get("security") is None  # not global — routes opt in
    assert s["paths"]["/public"]["get"].get("security") is None
    assert s["paths"]["/private"]["get"]["security"] == [{"bearerAuth": []}]


def test_oidc_security_scheme_openid_connect() -> None:
    router = Router()
    router.get("/admin", health, name="admin").secure("oidc")
    url = "http://localhost:8080/realms/arvel/.well-known/openid-configuration"
    with _serve({"security": {"oidc": {"openIdConnectUrl": url}}}, router) as c:
        s = c.get("/schema/openapi.json").json()
    scheme = s["components"]["securitySchemes"]["oidc"]
    assert scheme["type"] == "openIdConnect"
    assert scheme["openIdConnectUrl"] == url
    assert s["paths"]["/admin"]["get"]["security"] == [{"oidc": []}]


def test_security_default_true_applies_globally() -> None:
    router = Router()
    router.get("/health", health, name="health")
    with _serve({"security": {"bearer": {"default": True}}}, router) as c:
        s = c.get("/schema/openapi.json").json()
    assert s["security"] == [{"bearerAuth": []}]


def test_unknown_config_key_is_rejected() -> None:
    import msgspec

    router = Router()
    router.get("/health", health, name="health")
    # a typo'd key is caught, not silently dropped
    with pytest.raises(msgspec.ValidationError), _serve({"titel": "typo"}, router):
        pass


def test_secure_without_defined_scheme_warns() -> None:
    import structlog

    from arvel.http import HttpKernel

    app = Application()
    app.instance("config", Repository({"openapi": {}}))  # no security scheme defined
    set_application(app)
    router = Router()
    router.get("/private", health, name="private").secure("bearer")  # dangling reference
    kernel = HttpKernel(app)
    router.apply_to(kernel)
    try:
        with structlog.testing.capture_logs() as logs:
            kernel.build()
        assert any(e["event"] == "route_security_scheme_undefined" for e in logs)
    finally:
        set_application(None)

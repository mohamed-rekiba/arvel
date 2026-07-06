"""JSON:API through the served path: the media type on resource returns, and the errors[]
document for clients that ask for it."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from litestar.testing import TestClient

from arvel import Application
from arvel.database.resources import JsonApiResource
from arvel.kernel.application import set_application
from arvel.routing import Router

JSONAPI = "application/vnd.api+json"


class Thing:
    __primary_key__ = "id"

    def to_dict(self) -> dict[str, Any]:
        return {"id": 1, "name": "widget"}


class ThingResource(JsonApiResource[Thing]):
    resource_type = "things"


@contextmanager
def _client(router: Router) -> Iterator[TestClient[Any]]:
    # as_asgi() sets the process-global application; reset it so routes don't
    # bleed into tests that boot their own app afterwards
    app = Application()
    app.singleton("router", lambda _app: router)
    try:
        with TestClient(app.as_asgi()) as client:
            yield client
    finally:
        set_application(None)


def test_resource_return_gets_the_jsonapi_media_type() -> None:
    router = Router()
    router.get("/thing", lambda request: ThingResource(Thing()))
    with _client(router) as client:
        resp = client.get("/thing")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(JSONAPI)
    assert resp.json()["data"] == {
        "type": "things",
        "id": "1",
        "attributes": {"name": "widget"},
    }


def test_validation_failure_renders_jsonapi_errors() -> None:
    from arvel.validation import ValidationException

    def handler(request: Any) -> Any:
        raise ValidationException({"name": ["required"]}, status=422)

    router = Router()
    router.get("/fail", handler)
    with _client(router) as client:
        resp = client.get("/fail", headers={"accept": JSONAPI})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith(JSONAPI)
    assert resp.json()["errors"] == [
        {
            "status": "422",
            "detail": "required",
            "source": {"pointer": "/data/attributes/name"},
        }
    ]


def test_plain_json_clients_keep_the_existing_error_shape() -> None:
    from arvel.validation import ValidationException

    def handler(request: Any) -> Any:
        raise ValidationException({"name": ["required"]}, status=422)

    router = Router()
    router.get("/fail", handler)
    with _client(router) as client:
        resp = client.get("/fail", headers={"accept": "application/json"})
    assert resp.status_code == 422
    assert resp.json() == {
        "message": "Unprocessable Entity",
        "errors": {"name": ["required"]},
    }

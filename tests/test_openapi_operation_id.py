"""DR-0057 Fix 2 — a resource `update` route serves PUT+PATCH on one merged handler; a plain
string operationId collides across the two operations and Litestar's uniqueness check rejects
the whole document, so `openapi:export` fails for any app with an `api_resource`. A per-method
operationId callable (Litestar invokes it once per HTTP method) disambiguates without splitting
the handler; single-method routes keep the byte-identical plain-string id."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Controller, Router


class WidgetController(Controller):
    async def index(self, request: Any) -> dict[str, Any]:
        return {"action": "index"}

    async def show(self, request: Any, widget: str) -> dict[str, Any]:
        return {"action": "show", "id": widget}

    async def update(self, request: Any, widget: str) -> dict[str, Any]:
        return {"action": "update", "id": widget}

    async def destroy(self, request: Any, widget: str) -> dict[str, Any]:
        return {"action": "destroy", "id": widget}


def _client() -> TestClient[Any]:
    router = Router()
    router.api_resource("widgets", WidgetController)
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_api_resource_export_succeeds_with_distinct_update_operation_ids() -> None:
    with _client() as client:
        response = client.get("/schema/openapi.json")
        assert response.status_code == 200  # no duplicate-operationId rejection
        doc = response.json()
        update_ops = doc["paths"]["/widgets/{widget}"]
        put_id = update_ops["put"]["operationId"]
        patch_id = update_ops["patch"]["operationId"]
        assert put_id != patch_id
        assert put_id == "widgets.update_put"
        assert patch_id == "widgets.update_patch"


def test_single_method_route_operation_id_is_unchanged() -> None:
    with _client() as client:
        doc = client.get("/schema/openapi.json").json()
        assert doc["paths"]["/widgets"]["get"]["operationId"] == "widgets.index"
        assert doc["paths"]["/widgets/{widget}"]["get"]["operationId"] == "widgets.show"

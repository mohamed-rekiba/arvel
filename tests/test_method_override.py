"""HTML form method-spoofing (Laravel @method): a POST carrying ``_method=PUT|PATCH|DELETE`` is
routed as that verb by the MethodOverride ASGI middleware, so a ``<form method=post>`` can reach a
PUT/PATCH/DELETE route. The ``method_field()`` view global renders the hidden input."""

from __future__ import annotations

from typing import Any

import httpx

from arvel import Application, Route
from arvel.kernel import set_application
from arvel.kernel.bootstrap import bootstrap_app


async def _update(request: Any) -> dict[str, Any]:
    return {"verb": "PUT", "id": int(request.path_param("id"))}


async def _destroy(request: Any) -> dict[str, Any]:
    return {"verb": "DELETE", "id": int(request.path_param("id"))}


def _client() -> tuple[Application, httpx.ASGITransport]:
    app = (
        Application.configure(".")
        .with_config({"app": {"key": "base64:" + "A" * 43 + "=", "url": "http://test"}})
        .create()
    )
    bootstrap_app(app)
    Route.put("/items/{id:int}", _update, name="items.update")
    Route.delete("/items/{id:int}", _destroy, name="items.destroy")
    return app, httpx.ASGITransport(app=app.as_asgi())


async def test_form_post_is_routed_as_the_spoofed_method() -> None:
    _app, transport = _client()
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            put = await c.post("/items/5", data={"_method": "PUT", "name": "x"})
            assert put.status_code == 200 and put.json() == {"verb": "PUT", "id": 5}

            delete = await c.post("/items/9", data={"_method": "delete"})  # case-insensitive
            assert delete.status_code == 200 and delete.json() == {"verb": "DELETE", "id": 9}

            # a plain POST (no _method) is NOT spoofed → 405 (no POST route)
            assert (await c.post("/items/5", data={"name": "x"})).status_code == 405
            # a JSON POST body is left untouched (only urlencoded forms are inspected)
            assert (await c.post("/items/5", json={"_method": "PUT"})).status_code == 405
            # a real PUT still routes normally
            assert (await c.put("/items/5")).status_code == 200
    finally:
        set_application(None)


def test_method_field_global_renders_hidden_input() -> None:
    from arvel.views import ViewFactory, _method_field

    assert "method_field" in ViewFactory("resources/views").env.globals
    html = str(_method_field("patch"))
    assert html == '<input type="hidden" name="_method" value="PATCH">'

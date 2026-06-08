"""Raw model returns must honour ``__hidden__`` through the HTTP layer.

FastAPI encodes an Arvel ``Model`` as a plain dataclass — every column,
including ones marked ``__hidden__``. A bare ``return user`` would leak a
password hash or token. The Router normalises raw model returns through
``to_dict()`` so hidden columns stay hidden, matching Laravel.
"""

from __future__ import annotations

from typing import Any, cast

import httpx2 as httpx
from arvel.database.columns import id_, string
from arvel.database.model import Model
from pydantic import BaseModel
from starlette.testclient import TestClient


class Widget(Model):
    __tablename__ = "wi054_widgets"
    __hidden__ = ["secret"]
    id: int = id_()
    name: str = string(50)
    secret: str = string(100)


def _make_app() -> Any:
    from arvel.routing import Route, Router
    from fastapi import FastAPI

    Router.reset_singleton()

    @Route.get("/widget")
    async def show() -> Any:
        return Widget(name="public", secret="TOPSECRET")

    @Route.get("/widgets")
    async def index() -> Any:
        return [Widget(name="a", secret="x"), Widget(name="b", secret="y")]

    @Route.get("/payload")
    async def payload() -> Any:
        return {"ok": True, "count": 2}

    @Route.get("/nested")
    async def nested() -> Any:
        return {
            "user": Widget(name="pub", secret="LEAK"),
            "list": [Widget(name="a", secret="x")],
            "deep": {"inner": Widget(name="d", secret="y")},
        }

    for _f in (show, index, payload, nested):
        del _f  # registered via @Route.*; drop local bindings

    app = FastAPI()
    Router.singleton().register_with_app(app)
    return app


def _client(app: Any) -> httpx.Client:
    return cast("httpx.Client", TestClient(app))


def test_raw_model_return_hides_hidden_columns() -> None:
    app = _make_app()
    body = _client(app).get("/widget").json()
    assert body == {"id": None, "name": "public"}
    assert "secret" not in body


def test_list_of_models_hides_hidden_columns() -> None:
    app = _make_app()
    body = _client(app).get("/widgets").json()
    assert body == [{"id": None, "name": "a"}, {"id": None, "name": "b"}]
    assert all("secret" not in row for row in body)


def test_non_model_return_passes_through_untouched() -> None:
    app = _make_app()
    body = _client(app).get("/payload").json()
    assert body == {"ok": True, "count": 2}


def test_models_nested_in_dict_hide_hidden_columns() -> None:
    app = _make_app()
    body = _client(app).get("/nested").json()
    assert body == {
        "user": {"id": None, "name": "pub"},
        "list": [{"id": None, "name": "a"}],
        "deep": {"inner": {"id": None, "name": "d"}},
    }
    assert "secret" not in body["user"]
    assert "secret" not in body["list"][0]
    assert "secret" not in body["deep"]["inner"]


def test_pydantic_return_passes_through_untouched() -> None:
    from arvel.routing import Route, Router
    from fastapi import FastAPI

    class Out(BaseModel):
        name: str

    Router.reset_singleton()

    @Route.get("/typed")
    async def typed() -> Any:
        return Out(name="kept")

    del typed

    app = FastAPI()
    Router.singleton().register_with_app(app)
    assert _client(app).get("/typed").json() == {"name": "kept"}

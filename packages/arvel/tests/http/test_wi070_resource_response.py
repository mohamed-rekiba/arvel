"""FastAPI Response-compat for resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx
from arvel.database import Paginator
from arvel.http import JsonResource, ResourceResponse
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass
class _User:
    user_id: int
    email: str


class UserResource(JsonResource[_User]):
    def to_dict(self, request: Any) -> dict[str, Any]:
        return {"id": self.resource.user_id, "email": self.resource.email}


class _DummyRequest:
    url = None
    query_params: dict[str, str] = {}


class TestJsonResourceResponse:
    def test_response_is_starlette_response(self) -> None:
        body = UserResource(_User(1, "a@x.io")).response(_DummyRequest())
        assert isinstance(body, Response)
        assert isinstance(body, JSONResponse)
        assert isinstance(body, ResourceResponse)

    def test_response_body_matches_to_dict(self) -> None:
        req = _DummyRequest()
        resource = UserResource(_User(1, "a@x.io"))
        resp = resource.response(req)
        assert resp.body == b'{"id":1,"email":"a@x.io"}'

    def test_response_honours_status_and_headers(self) -> None:
        resp = UserResource(_User(1, "a@x.io")).response(
            _DummyRequest(),
            status_code=201,
            headers={"X-Trace": "abc"},
        )
        assert resp.status_code == 201
        assert resp.headers["x-trace"] == "abc"

    def test_additional_survives_response_chain(self) -> None:
        resp = (
            UserResource(_User(1, "a@x.io"))
            .additional({"meta": {"v": "1"}})
            .response(_DummyRequest())
        )
        assert b'"meta"' in resp.body


class TestResourceCollectionResponse:
    def test_list_collection_response_envelope(self) -> None:
        coll = UserResource.collection([_User(1, "a@x.io")])
        resp = coll.response(_DummyRequest())
        assert isinstance(resp, ResourceResponse)
        assert resp.body == b'{"data":[{"id":1,"email":"a@x.io"}]}'

    def test_paginator_collection_response_envelope(self) -> None:
        page: Paginator[_User] = Paginator(
            items=[_User(1, "a@x.io")],
            total=1,
            per_page=10,
            current_page=1,
        )
        coll = UserResource.collection(page)
        resp = coll.response(_DummyRequest())
        assert b'"meta"' in resp.body
        assert b'"links"' in resp.body
        assert b'"data"' in resp.body

    def test_additional_on_collection_before_response(self) -> None:
        coll = UserResource.collection([_User(1, "a@x.io")])
        resp = coll.additional({"meta": {"trace": "t1"}}).response(_DummyRequest())
        assert b'"trace":"t1"' in resp.body


class TestFastAPIHandlerReturn:
    def test_handler_can_return_resource_response(self) -> None:
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        app = FastAPI()

        @app.get("/users")
        async def handler(request: Request) -> ResourceResponse:
            users = [_User(1, "a@x.io"), _User(2, "b@x.io")]
            return UserResource.collection(users).response(request)

        del handler
        resp = cast("httpx.Client", TestClient(app)).get("/users")
        assert resp.status_code == 200
        assert resp.json() == {
            "data": [
                {"id": 1, "email": "a@x.io"},
                {"id": 2, "email": "b@x.io"},
            ]
        }

    def test_single_resource_handler_return(self) -> None:
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        app = FastAPI()

        @app.get("/users/{user_id}")
        async def handler(user_id: int, request: Request) -> JSONResponse:
            return UserResource(_User(user_id, "x@y.io")).response(request, status_code=200)

        del handler
        resp = cast("httpx.Client", TestClient(app)).get("/users/7")
        assert resp.status_code == 200
        assert resp.json() == {"id": 7, "email": "x@y.io"}

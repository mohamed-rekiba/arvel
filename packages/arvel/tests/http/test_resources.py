"""FR-002-010, FR-002-011, FR-002-012 — JsonResource + ResourceCollection + opt-in schemas."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel


class _UserDict(dict[str, Any]):
    """Stand-in domain object."""


def test_json_resource_subclass_returns_dict() -> None:
    from arvel.http.resources import JsonResource

    user = _UserDict(id=1, email="x@example.com")

    class UserResource(JsonResource[_UserDict]):
        def to_dict(self, request: Any) -> dict[str, object]:
            return {"id": self.resource["id"]}

    res = UserResource(user)
    assert res.to_dict(_DummyRequest()) == {"id": 1}


def test_json_resource_exposes_resource_attribute() -> None:
    from arvel.http.resources import JsonResource

    class UR(JsonResource[_UserDict]):
        def to_dict(self, request: Any) -> dict[str, object]:
            return {}

    u = _UserDict(id=1)
    assert UR(u).resource is u


def test_resource_collection_envelope_is_data_by_default() -> None:
    from arvel.http.resources import JsonResource

    class UR(JsonResource[_UserDict]):
        def to_dict(self, request: Any) -> dict[str, object]:
            return {"id": self.resource["id"]}

    coll = UR.collection([_UserDict(id=1), _UserDict(id=2)])
    body = coll.to_dict(_DummyRequest())
    assert body == {"data": [{"id": 1}, {"id": 2}]}


def test_resource_collection_wrap_can_be_overridden() -> None:
    from arvel.http.resources import JsonResource, ResourceCollection

    class UR(JsonResource[_UserDict]):
        def to_dict(self, request: Any) -> dict[str, object]:
            return {"id": self.resource["id"]}

    class PaginatedCollection(ResourceCollection[_UserDict]):
        def wrap(self, data: list[dict[str, object]]) -> dict[str, object]:
            return {"data": data, "meta": {"count": len(data)}}

    coll = PaginatedCollection([_UserDict(id=1)], UR)
    body = coll.to_dict(_DummyRequest())
    assert body == {"data": [{"id": 1}], "meta": {"count": 1}}


def test_json_resource_schema_classvar_is_optional() -> None:
    from arvel.http.resources import JsonResource

    class UR(JsonResource[_UserDict]):
        def to_dict(self, request: Any) -> dict[str, object]:
            return {}

    assert UR.schema is None


def test_json_resource_schema_classvar_can_be_set() -> None:
    from arvel.http.resources import JsonResource

    class UserPublic(BaseModel):
        id: int

    class UR(JsonResource[_UserDict]):
        schema: ClassVar[type[BaseModel] | None] = UserPublic

        def to_dict(self, request: Any) -> dict[str, object]:
            return {"id": self.resource["id"]}

    assert UR.schema is UserPublic


class _DummyRequest:
    """Stand-in starlette.Request — we only call to_dict so the receiver is unused."""

"""follow-up: ``.additional({...})``.

Resources and resource collections accept extra root-level keys via a
fluent ``.additional(extra)`` method. Merge happens AFTER the default
envelope is built, so caller-supplied extras win on key clashes.

Covers:
- ``JsonResource.additional`` adds keys to the dict the resource returns.
- ``ResourceCollection.additional`` adds keys to the envelope for both
  the list path and the paginator path.
- Chaining returns ``Self`` so callers can continue the chain.
- Extras override default-envelope keys when they conflict.
- Extras are per-instance — calling ``.additional`` on one collection
  doesn't bleed into another.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arvel.database import Paginator
from arvel.http import JsonResource


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


# JsonResource.additional


class TestJsonResourceAdditional:
    def test_adds_extra_keys_to_dict(self) -> None:
        resource = UserResource(_User(user_id=1, email="a@x.io"))
        body = resource.additional({"meta": {"version": "1.0"}}).to_dict(_DummyRequest())
        assert body == {
            "id": 1,
            "email": "a@x.io",
            "meta": {"version": "1.0"},
        }

    def test_extra_overrides_default_key(self) -> None:
        resource = UserResource(_User(user_id=1, email="a@x.io"))
        body = resource.additional({"email": "override@x.io"}).to_dict(_DummyRequest())
        assert body["email"] == "override@x.io"

    def test_chainable_returns_self(self) -> None:
        resource = UserResource(_User(user_id=1, email="a@x.io"))
        same = resource.additional({"a": 1}).additional({"b": 2})
        body = same.to_dict(_DummyRequest())
        assert body["a"] == 1
        assert body["b"] == 2


# ResourceCollection.additional — list path


class TestResourceCollectionAdditionalList:
    def test_adds_extra_keys_alongside_data(self) -> None:
        coll = UserResource.collection([_User(user_id=1, email="a@x.io")])
        body = coll.additional({"meta": {"v": "1"}}).to_dict(_DummyRequest())
        assert body["data"] == [{"id": 1, "email": "a@x.io"}]
        assert body["meta"] == {"v": "1"}

    def test_extras_dont_leak_across_collections(self) -> None:
        coll_a = UserResource.collection([_User(user_id=1, email="a@x.io")])
        coll_b = UserResource.collection([_User(user_id=2, email="b@x.io")])

        coll_a.additional({"only_a": True})

        body_b = coll_b.to_dict(_DummyRequest())
        assert "only_a" not in body_b


# ResourceCollection.additional — paginator path


class TestResourceCollectionAdditionalPaginator:
    def test_extras_merge_into_paginator_envelope(self) -> None:
        page: Paginator[_User] = Paginator(
            items=[_User(user_id=1, email="a@x.io")],
            total=1,
            per_page=10,
            current_page=1,
        )
        coll = UserResource.collection(page)
        body = coll.additional({"meta": {"trace_id": "abc"}}).to_dict(_DummyRequest())

        # The paginator's own data + meta + links keys are still there.
        assert body["data"] == [{"id": 1, "email": "a@x.io"}]
        assert "meta" in body
        assert "links" in body
        # And the extras live alongside.
        assert body["meta"] == {"trace_id": "abc"}

    def test_extra_can_override_paginator_meta(self) -> None:
        page: Paginator[_User] = Paginator(
            items=[_User(user_id=1, email="a@x.io")],
            total=1,
            per_page=10,
            current_page=1,
        )
        coll = UserResource.collection(page)
        body = coll.additional({"data": ["overridden"]}).to_dict(_DummyRequest())
        assert body["data"] == ["overridden"]

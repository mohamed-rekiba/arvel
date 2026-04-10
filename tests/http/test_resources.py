"""Tests for API Resources and Transformers — Epic 17.

FR-001: JsonResource base class (to_dict, to_response, __wrap__, additional)
FR-002: Conditional field helpers (when, when_loaded, when_not_null)
FR-003: Relationship load detection (is_relation_loaded on ArvelModel)
FR-004: ResourceCollection (list, PaginatedResult, CursorResult, additional)
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.data.collection import ArvelCollection
from arvel.data.pagination import CursorResult, PaginatedResult
from arvel.http.resources import MISSING, JsonResource

# ──── Minimal stub models (no DB needed for resource tests) ────


class _StubModel:
    """Minimal model stub with model_dump() for resource tests."""

    id: int
    name: str
    email: str
    bio: str | None
    is_admin: bool
    admin_since: str | None
    title: str
    body: str
    posts: list[Any]
    profile: _StubModel | None
    _loaded_relations: set[str]

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)

    def model_dump(
        self,
        *,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
        include_relations: bool | list[str] = False,
    ) -> dict[str, Any]:
        result = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        if include is not None:
            result = {k: v for k, v in result.items() if k in include}
        if exclude is not None:
            result = {k: v for k, v in result.items() if k not in exclude}
        return result

    def is_relation_loaded(self, name: str) -> bool:
        return name in getattr(self, "_loaded_relations", set())


def _make_user(
    *,
    id: int = 1,  # noqa: A002
    name: str = "Alice",
    email: str = "alice@example.com",
    bio: str | None = None,
    is_admin: bool = False,
    admin_since: str | None = None,
    posts: list[Any] | None = None,
    loaded_relations: set[str] | None = None,
) -> _StubModel:
    user = _StubModel(
        id=id,
        name=name,
        email=email,
        bio=bio,
        is_admin=is_admin,
        admin_since=admin_since,
        posts=posts if posts is not None else [],
    )
    object.__setattr__(user, "_loaded_relations", loaded_relations or set())
    return user


def _make_post(*, id: int = 1, title: str = "Hello", body: str = "World") -> _StubModel:  # noqa: A002
    return _StubModel(id=id, title=title, body=body)


# ──── Test Resources ────


class UserResource(JsonResource["_StubModel"]):
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.resource.id,
            "name": self.resource.name,
            "email": self.resource.email,
        }


class UserWithConditionalsResource(JsonResource["_StubModel"]):
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.resource.id,
            "name": self.resource.name,
            "admin_since": self.when(self.resource.is_admin, self.resource.admin_since),
            "bio": self.when_not_null("bio"),
            "posts": self.when_loaded("posts", PostResource),
        }


class PostResource(JsonResource["_StubModel"]):
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.resource.id,
            "title": self.resource.title,
        }


class DefaultResource(JsonResource["_StubModel"]):
    """Resource that doesn't override to_dict — uses default model_dump()."""

    pass


class UnwrappedResource(JsonResource["_StubModel"]):
    __wrap__: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.resource.id, "name": self.resource.name}


class ProfileResource(JsonResource["_StubModel"]):
    def to_dict(self) -> dict[str, Any]:
        return {"id": self.resource.id, "bio": self.resource.bio}


# ============================================================================
# FR-001: JsonResource Base Class
# ============================================================================


class TestJsonResourceBase:
    """AC-001.1 through AC-001.6."""

    def test_to_dict_with_custom_override_returns_specified_fields(self) -> None:
        """AC-001.1: Custom to_dict returns resource's specified fields."""
        user = _make_user()
        result = UserResource(user).to_dict()
        assert result == {"id": 1, "name": "Alice", "email": "alice@example.com"}

    def test_default_to_dict_uses_model_dump(self) -> None:
        """AC-001.2: Without to_dict override, all model columns are included."""
        user = _make_user(id=5, name="Bob", email="bob@test.com", bio="A bio")
        result = DefaultResource(user).to_dict()
        assert result["id"] == 5
        assert result["name"] == "Bob"
        assert result["email"] == "bob@test.com"
        assert result["bio"] == "A bio"

    def test_to_response_wraps_with_data_key_by_default(self) -> None:
        """AC-001.3: Default __wrap__ = 'data' wraps the output."""
        user = _make_user()
        result = UserResource(user).to_response()
        assert "data" in result
        assert result["data"] == {"id": 1, "name": "Alice", "email": "alice@example.com"}

    def test_to_response_no_wrap_when_wrap_is_none(self) -> None:
        """AC-001.4: __wrap__ = None returns dict directly without wrapping."""
        user = _make_user()
        result = UnwrappedResource(user).to_response()
        assert result == {"id": 1, "name": "Alice"}
        assert "data" not in result

    def test_additional_merges_metadata_at_top_level(self) -> None:
        """AC-001.5: .additional() merges extra data into the response."""
        user = _make_user()
        result = UserResource(user).additional({"meta": "value"}).to_response()
        assert result["data"] == {"id": 1, "name": "Alice", "email": "alice@example.com"}
        assert result["meta"] == "value"

    def test_additional_merges_with_unwrapped_resource(self) -> None:
        """AC-001.5 (unwrapped variant): additional() works without wrapping."""
        user = _make_user()
        result = UnwrappedResource(user).additional({"extra": True}).to_response()
        assert result["id"] == 1
        assert result["name"] == "Alice"
        assert result["extra"] is True

    def test_resource_attribute_preserves_instance(self) -> None:
        """AC-001.6: resource attribute holds the original model instance."""
        user = _make_user(id=42)
        resource = UserResource(user)
        assert resource.resource is user
        assert resource.resource.id == 42

    def test_additional_returns_self_for_chaining(self) -> None:
        """Fluent API: additional() returns Self."""
        user = _make_user()
        resource = UserResource(user)
        result = resource.additional({"a": 1})
        assert result is resource


# ============================================================================
# FR-002: Conditional Field Helpers
# ============================================================================


class TestConditionalFieldWhen:
    """AC-002.1, AC-002.2."""

    def test_when_true_includes_value(self) -> None:
        """AC-002.1: when condition is true, value is included."""
        user = _make_user(is_admin=True, admin_since="2024-01-01")
        result = UserWithConditionalsResource(user).to_response()
        assert result["data"]["admin_since"] == "2024-01-01"

    def test_when_false_excludes_field(self) -> None:
        """AC-002.1: when condition is false, key is absent (not None)."""
        user = _make_user(is_admin=False, admin_since=None)
        result = UserWithConditionalsResource(user).to_response()
        assert "admin_since" not in result["data"]

    def test_when_false_with_default_includes_default(self) -> None:
        """AC-002.2: when false with default, default is included."""
        user = _make_user()
        resource = JsonResource(user)
        value = resource.when(False, "primary", default="fallback")
        assert value == "fallback"

    def test_when_false_without_default_returns_missing(self) -> None:
        """when false without default returns MISSING sentinel."""
        user = _make_user()
        resource = JsonResource(user)
        value = resource.when(False, "anything")
        assert value is MISSING


class TestConditionalFieldWhenLoaded:
    """AC-002.3, AC-002.4, AC-002.6."""

    def test_when_loaded_includes_transformed_collection(self) -> None:
        """AC-002.3: when relationship IS loaded, items are transformed."""
        posts = [_make_post(id=1, title="First"), _make_post(id=2, title="Second")]
        user = _make_user(posts=posts, loaded_relations={"posts"})
        result = UserWithConditionalsResource(user).to_response()
        assert result["data"]["posts"] == [
            {"id": 1, "title": "First"},
            {"id": 2, "title": "Second"},
        ]

    def test_when_loaded_excludes_when_not_loaded(self) -> None:
        """AC-002.3: when relationship is NOT loaded, key is absent."""
        user = _make_user(loaded_relations=set())
        result = UserWithConditionalsResource(user).to_response()
        assert "posts" not in result["data"]

    def test_when_loaded_single_model_not_wrapped_in_list(self) -> None:
        """AC-002.4: has_one/belongs_to returns single transformed model, not list."""
        profile = _StubModel(id=1, bio="Hello world")
        object.__setattr__(profile, "_loaded_relations", set())
        user = _StubModel(
            id=1,
            name="Alice",
            profile=profile,
            _loaded_relations={"profile"},
        )

        class UserWithProfileResource(JsonResource["_StubModel"]):
            def to_dict(self) -> dict[str, Any]:
                return {
                    "id": self.resource.id,
                    "profile": self.when_loaded("profile", ProfileResource),
                }

        result = UserWithProfileResource(user).to_response()
        assert result["data"]["profile"] == {"id": 1, "bio": "Hello world"}
        assert not isinstance(result["data"]["profile"], list)

    def test_when_loaded_without_resource_class_returns_raw(self) -> None:
        """when_loaded without resource_class returns raw value."""
        posts = [_make_post(id=1, title="Raw")]
        user = _make_user(posts=posts, loaded_relations={"posts"})
        resource = JsonResource(user)
        value = resource.when_loaded("posts")
        assert value == posts

    def test_when_loaded_nonexistent_relationship_raises(self) -> None:
        """AC-002.6: non-existent relationship raises ValueError."""
        user = _make_user()
        resource = UserWithConditionalsResource(user)
        with pytest.raises(ValueError, match="nonexistent"):
            resource.when_loaded("nonexistent")


class TestConditionalFieldWhenNotNull:
    """AC-002.5."""

    def test_when_not_null_includes_value_when_present(self) -> None:
        """AC-002.5: when value is not None, it is included."""
        user = _make_user(bio="My bio")
        result = UserWithConditionalsResource(user).to_response()
        assert result["data"]["bio"] == "My bio"

    def test_when_not_null_excludes_when_none(self) -> None:
        """AC-002.5: when value is None, key is absent."""
        user = _make_user(bio=None)
        result = UserWithConditionalsResource(user).to_response()
        assert "bio" not in result["data"]


# ============================================================================
# FR-003: Relationship Load Detection (tested via stub; DB integration in data/)
# ============================================================================


class TestIsRelationLoaded:
    """AC-003.1, AC-003.2, AC-003.3."""

    def test_loaded_relation_returns_true(self) -> None:
        """AC-003.1: eagerly loaded relationship returns True."""
        user = _make_user(loaded_relations={"posts"})
        assert user.is_relation_loaded("posts") is True

    def test_unloaded_relation_returns_false(self) -> None:
        """AC-003.2: unloaded relationship returns False."""
        user = _make_user(loaded_relations=set())
        assert user.is_relation_loaded("posts") is False

    def test_nonexistent_relation_returns_false(self) -> None:
        """AC-003.3: non-existent relationship returns False."""
        user = _make_user()
        assert user.is_relation_loaded("foo") is False


# ============================================================================
# FR-004: Resource Collection and Pagination
# ============================================================================


class TestResourceCollection:
    """AC-004.1 through AC-004.6."""

    def test_collection_from_list(self) -> None:
        """AC-004.1: plain list transformed via resource."""
        users = [_make_user(id=1, name="A"), _make_user(id=2, name="B")]
        result = UserResource.collection(users).to_response()
        assert isinstance(result, dict)
        assert result["data"] == [
            {"id": 1, "name": "A", "email": "alice@example.com"},
            {"id": 2, "name": "B", "email": "alice@example.com"},
        ]

    def test_collection_from_arvel_collection(self) -> None:
        """AC-004.1: ArvelCollection works like a list."""
        users = ArvelCollection([_make_user(id=3, name="C")])
        result = UserResource.collection(users).to_response()
        assert isinstance(result, dict)
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == 3

    def test_collection_from_paginated_result(self) -> None:
        """AC-004.2: PaginatedResult includes pagination metadata."""
        users = [_make_user(id=i, name=f"U{i}") for i in range(1, 4)]
        paginated = PaginatedResult(data=users, total=10, page=1, per_page=3)
        result = UserResource.collection(paginated).to_response()
        assert isinstance(result, dict)

        assert len(result["data"]) == 3
        assert result["meta"]["total"] == 10
        assert result["meta"]["page"] == 1
        assert result["meta"]["per_page"] == 3
        assert result["meta"]["last_page"] == 4
        assert result["meta"]["has_more"] is True

    def test_collection_from_cursor_result(self) -> None:
        """AC-004.3: CursorResult includes cursor metadata."""
        users = [_make_user(id=1), _make_user(id=2)]
        cursor = CursorResult(data=users, next_cursor="abc123", has_more=True)
        result = UserResource.collection(cursor).to_response()
        assert isinstance(result, dict)

        assert len(result["data"]) == 2
        assert result["meta"]["next_cursor"] == "abc123"
        assert result["meta"]["has_more"] is True

    def test_collection_additional_merges_at_top_level(self) -> None:
        """AC-004.4: additional() on collection merges at top level."""
        users = [_make_user()]
        result = UserResource.collection(users).additional({"stats": {"active": 42}}).to_response()
        assert isinstance(result, dict)
        assert result["stats"] == {"active": 42}

    def test_collection_no_wrap_returns_plain_list(self) -> None:
        """AC-004.5: __wrap__ = None returns plain list."""
        users = [_make_user(id=1), _make_user(id=2)]
        result = UnwrappedResource.collection(users).to_response()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_collection_empty_list(self) -> None:
        """AC-004.6: empty list returns {"data": []}."""
        result = UserResource.collection([]).to_response()
        assert result == {"data": []}

    def test_collection_additional_returns_self_for_chaining(self) -> None:
        """Fluent API: additional() returns Self."""
        collection = UserResource.collection([])
        result = collection.additional({"a": 1})
        assert result is collection

    def test_collection_paginated_result_no_more_pages(self) -> None:
        """PaginatedResult on last page: has_more is False."""
        users = [_make_user(id=1)]
        paginated = PaginatedResult(data=users, total=1, page=1, per_page=20)
        result = UserResource.collection(paginated).to_response()
        assert isinstance(result, dict)
        assert result["meta"]["has_more"] is False
        assert result["meta"]["last_page"] == 1

    def test_collection_cursor_result_no_next(self) -> None:
        """CursorResult without next page: next_cursor is None, has_more is False."""
        users = [_make_user(id=1)]
        cursor = CursorResult(data=users, next_cursor=None, has_more=False)
        result = UserResource.collection(cursor).to_response()
        assert isinstance(result, dict)
        assert result["meta"]["next_cursor"] is None
        assert result["meta"]["has_more"] is False


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Additional edge case coverage."""

    def test_missing_sentinel_is_falsy(self) -> None:
        """MISSING is falsy for boolean checks."""
        assert not MISSING
        assert bool(MISSING) is False

    def test_missing_sentinel_is_singleton(self) -> None:
        """MISSING is always the same instance."""
        from arvel.http.resources import MISSING as MISSING2

        assert MISSING is MISSING2

    def test_to_response_strips_nested_missing_values(self) -> None:
        """MISSING values inside nested dicts are also stripped."""

        class NestedResource(JsonResource["_StubModel"]):
            def to_dict(self) -> dict[str, Any]:
                return {
                    "id": self.resource.id,
                    "nested": {
                        "present": "yes",
                        "absent": MISSING,
                    },
                }

        user = _make_user()
        result = NestedResource(user).to_response()
        assert result["data"]["nested"] == {"present": "yes"}

    def test_collection_with_conditionals_strips_missing(self) -> None:
        """Collection items have MISSING values stripped."""
        user = _make_user(bio=None, loaded_relations=set())
        result = UserWithConditionalsResource.collection([user]).to_response()
        assert isinstance(result, dict)
        item = result["data"][0]
        assert "bio" not in item
        assert "posts" not in item

    def test_when_loaded_empty_list_is_included(self) -> None:
        """An eagerly loaded but empty relationship is included as []."""
        user = _make_user(posts=[], loaded_relations={"posts"})
        result = UserWithConditionalsResource(user).to_response()
        assert result["data"]["posts"] == []

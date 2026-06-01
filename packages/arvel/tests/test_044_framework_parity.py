"""Failing tests for Framework Parity stories.

Run BEFORE implementation — all tests here MUST FAIL (RED state).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from arvel.database.query import QueryBuilder


def _bare_query_builder() -> QueryBuilder[Any]:
    """Construct a QueryBuilder wired to the ``object`` base class.

    Tests override ``_model`` and ``_stmt`` as needed via ``object.__setattr__``.
    Going through ``__init__`` (rather than ``__new__``) keeps both mypy and
    pyright happy on the generic parameter.
    """
    from arvel.database.query import QueryBuilder
    from sqlalchemy import select, text

    return QueryBuilder[Any](object, stmt=select(text("1")))


# Named route URL generation


class TestStory3NamedRoutes:
    """Named route URL generation via route('name', **params)."""

    def test_route_helper_returns_url_for_simple_name(self) -> None:
        from arvel.routing import Route, Router
        from arvel.routing import route as route_helper

        Router.reset_singleton()

        @Route.get("/users/{user_id}", name="users.show")
        async def handler(user_id: int) -> dict[str, Any]:
            return {}

        del handler  # registered via @Route.get; drop local binding

        url = route_helper("users.show", user_id=42)
        assert url == "/users/42"

    def test_route_helper_raises_for_unknown_name(self) -> None:
        from arvel.routing import RouteNotFoundError, Router
        from arvel.routing import route as route_helper

        Router.reset_singleton()
        with pytest.raises(RouteNotFoundError):
            route_helper("nonexistent")

    def test_route_helper_substitutes_multiple_params(self) -> None:
        from arvel.routing import Route, Router
        from arvel.routing import route as route_helper

        Router.reset_singleton()

        @Route.get("/orders/{order_id}/items/{item_id}", name="orders.items.show")
        async def handler(order_id: int, item_id: int) -> dict[str, Any]:
            return {}

        del handler  # registered via @Route.get; drop local binding

        url = route_helper("orders.items.show", order_id=1, item_id=2)
        assert url == "/orders/1/items/2"


class TestStory4ContainerCall:
    """Container.call() and Container.acall() for method injection."""

    def test_call_resolves_parameters_from_container(self) -> None:
        from arvel.container import Container

        container = Container()

        class MyDep:
            value = "injected"

        container.singleton(MyDep)

        class MyService:
            def process(self, dep: MyDep, item_id: int) -> str:
                return f"{dep.value}:{item_id}"

        result = container.call(MyService, "process", overrides={"item_id": 42})
        assert result == "injected:42"

    def test_call_instantiates_class_via_container(self) -> None:
        from arvel.container import Container

        container = Container()

        class MyService:
            def greet(self) -> str:
                return "hello"

        result = container.call(MyService, "greet")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_acall_supports_async_methods(self) -> None:
        from arvel.container import Container

        container = Container()

        class MyService:
            async def fetch(self) -> str:
                return "async_result"

        result = await container.acall(MyService, "fetch")
        assert result == "async_result"


# abort helpers


class TestStory6AbortHelpers:
    """abort(), abort_if(), abort_unless() importable helpers."""

    def test_abort_raises_with_status_and_default_message(self) -> None:
        from arvel.http.exceptions import HttpException
        from arvel.support import abort

        with pytest.raises(HttpException) as exc_info:
            abort(404)
        assert exc_info.value.status_code == 404

    def test_abort_raises_with_custom_message(self) -> None:
        from arvel.http.exceptions import HttpException
        from arvel.support import abort

        with pytest.raises(HttpException) as exc_info:
            abort(404, "Custom message")
        assert "Custom message" in str(exc_info.value)

    def test_abort_if_raises_when_condition_truthy(self) -> None:
        from arvel.http.exceptions import HttpException
        from arvel.support import abort_if

        with pytest.raises(HttpException) as exc_info:
            abort_if(True, 422, "Invalid")
        assert exc_info.value.status_code == 422

    def test_abort_if_does_not_raise_when_condition_falsy(self) -> None:
        from arvel.support import abort_if

        abort_if(False, 422)  # should not raise

    def test_abort_unless_raises_when_condition_falsy(self) -> None:
        from arvel.http.exceptions import HttpException
        from arvel.support import abort_unless

        with pytest.raises(HttpException) as exc_info:
            abort_unless(False, 403)
        assert exc_info.value.status_code == 403

    def test_abort_unless_does_not_raise_when_condition_truthy(self) -> None:
        from arvel.support import abort_unless

        abort_unless(True, 403)  # should not raise

    def test_abort_403_maps_to_forbidden(self) -> None:
        from arvel.http.exceptions import HttpException
        from arvel.support import abort

        with pytest.raises(HttpException) as exc_info:
            abort(403)
        assert exc_info.value.status_code == 403


# model_serialize datetime


class TestStory8ModelSerializeDatetime:
    """model_serialize() auto-converts datetime fields to ISO 8601 strings."""

    def _make_instance(self, data: dict[str, Any], hidden: list[str] | None = None) -> Any:
        """Create a minimal model-like object without triggering SQLAlchemy mapping."""
        from arvel.database.model import Model

        # Use object.__new__ to bypass __init__ and dataclass machinery.
        # Directly set __dict__ to simulate a hydrated ORM instance.
        class _M(Model):
            __tablename__ = "test_model_serialize"
            __abstract__ = True  # avoids SQLAlchemy mapper registration

        inst = object.__new__(_M)
        for k, v in data.items():
            object.__setattr__(inst, k, v)
        if hidden is not None:
            type(inst).__hidden__ = hidden
        return inst

    def test_model_serialize_converts_datetime_to_iso8601(self) -> None:
        dt = datetime(2026, 5, 24, 9, 30, 0, tzinfo=UTC)
        inst = self._make_instance({"id": 1, "created_at": dt})
        result = inst.model_serialize()
        assert result["created_at"] == "2026-05-24T09:30:00+00:00"

    def test_model_serialize_none_datetime_is_null(self) -> None:
        inst = self._make_instance({"id": 1, "deleted_at": None})
        result = inst.model_serialize()
        assert result["deleted_at"] is None

    def test_model_serialize_decimal_to_float(self) -> None:
        inst = self._make_instance({"id": 1, "price": Decimal("9.99")})
        result = inst.model_serialize()
        assert isinstance(result["price"], float)
        assert abs(result["price"] - 9.99) < 1e-9

    def test_model_serialize_excludes_hidden_fields(self) -> None:
        inst = self._make_instance(
            {"id": 1, "name": "Alice", "password": "secret"}, hidden=["password"]
        )
        result = inst.model_serialize()
        assert "password" not in result
        assert result["name"] == "Alice"


# partial): shared_lock FOR SHARE


class TestStory9SharedLock:
    """shared_lock() sets a read-lock flag distinct from lock_for_update."""

    def _bare_qb(self) -> Any:
        """QueryBuilder with no real SQLAlchemy session needed — flag checks only."""
        from sqlalchemy import select, text
        from sqlalchemy.orm import DeclarativeBase

        class _FakeBase(DeclarativeBase):
            pass

        del _FakeBase  # type-stub for SQLAlchemy import; not used directly

        # Bypass SQLAlchemy mapping — only need the _lock flags.
        qb = _bare_query_builder()
        object.__setattr__(qb, "_model", object)
        object.__setattr__(qb, "_stmt", select(text("1")))
        object.__setattr__(qb, "_lock_for_update", False)
        object.__setattr__(qb, "_lock_shared", False)
        object.__setattr__(qb, "_removed_global_scopes", set())
        object.__setattr__(qb, "_remove_all_global_scopes", False)
        object.__setattr__(qb, "_ctes", [])
        object.__setattr__(qb, "_select_columns", None)
        object.__setattr__(qb, "_raw_select_expr", None)
        return qb

    def test_shared_lock_sets_lock_shared_flag(self) -> None:
        qb = self._bare_qb()
        locked = qb.shared_lock()
        assert locked._lock_shared is True
        assert locked._lock_for_update is False

    def test_lock_for_update_sets_lock_for_update_flag(self) -> None:
        qb = self._bare_qb()
        locked = qb.lock_for_update()
        assert locked._lock_for_update is True
        assert locked._lock_shared is False

    def test_lock_for_update_renders_for_update_in_postgresql_sql(self) -> None:
        qb = self._bare_qb()
        sql = qb.lock_for_update().to_sql(dialect="postgresql")
        assert "FOR UPDATE" in sql

    def test_shared_lock_renders_for_share_in_postgresql_sql(self) -> None:
        qb = self._bare_qb()
        sql = qb.shared_lock().to_sql(dialect="postgresql")
        assert "FOR SHARE" in sql


# first_or_create / update_or_create


class TestStory11UpsertHelpers:
    """first_or_create(), first_or_new() on QueryBuilder."""

    @pytest.mark.asyncio
    async def test_first_or_create_returns_existing_when_found(self) -> None:

        existing = object()

        class _Fake:
            pass

        qb = _bare_query_builder()
        object.__setattr__(qb, "_model", _Fake)
        object.__setattr__(qb, "where", MagicMock(return_value=qb))
        qb.first = AsyncMock(return_value=existing)  # type: ignore[method-assign]
        result = await qb.first_or_create({"name": "Alice"})
        assert result is existing

    @pytest.mark.asyncio
    async def test_first_or_create_merges_attributes_into_create_when_not_found(self) -> None:

        created = object()

        class _Fake:
            create = AsyncMock(return_value=created)

        qb = _bare_query_builder()
        object.__setattr__(qb, "_model", _Fake)
        object.__setattr__(qb, "where", MagicMock(return_value=qb))
        qb.first = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = await qb.first_or_create({"email": "b@b.com"}, {"name": "Bob"})
        assert result is created
        # Searched attributes AND values both reach create — Laravel firstOrCreate semantics.
        _Fake.create.assert_awaited_once_with(email="b@b.com", name="Bob")

    @pytest.mark.asyncio
    async def test_first_or_new_returns_unsaved_instance_with_merged_attributes(self) -> None:

        class _FakeUser:
            def __init__(self, **attrs: object) -> None:
                self.attrs = attrs

        qb = _bare_query_builder()
        object.__setattr__(qb, "_model", _FakeUser)
        object.__setattr__(qb, "where", MagicMock(return_value=qb))
        qb.first = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = await qb.first_or_new({"email": "c@c.com"}, {"name": "Charlie"})
        assert isinstance(result, _FakeUser)
        assert result.attrs == {"email": "c@c.com", "name": "Charlie"}

    @pytest.mark.asyncio
    async def test_update_or_create_updates_existing_row(self) -> None:
        existing = MagicMock()
        existing.save = AsyncMock()

        class _Fake:
            pass

        qb = _bare_query_builder()
        object.__setattr__(qb, "_model", _Fake)
        object.__setattr__(qb, "where", MagicMock(return_value=qb))
        qb.first = AsyncMock(return_value=existing)  # type: ignore[method-assign]

        result = await qb.update_or_create({"email": "a@b.com"}, {"name": "Updated"})

        assert result is existing
        existing.fill.assert_called_once_with(name="Updated")
        existing.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_or_create_creates_when_missing(self) -> None:
        created = object()

        class _Fake:
            create = AsyncMock(return_value=created)

        qb = _bare_query_builder()
        object.__setattr__(qb, "_model", _Fake)
        object.__setattr__(qb, "where", MagicMock(return_value=qb))
        qb.first = AsyncMock(return_value=None)  # type: ignore[method-assign]

        result = await qb.update_or_create({"email": "a@b.com"}, {"name": "Alice"})

        assert result is created
        _Fake.create.assert_awaited_once_with(email="a@b.com", name="Alice")


class TestStory10WhereJsonContains:
    """where_json_contains() emits PostgreSQL containment SQL."""

    def test_where_json_contains_renders_postgresql_contains_operator(self) -> None:
        from sqlalchemy import JSON, Column, Integer, Table
        from sqlalchemy.orm import registry

        mapper_registry = registry()
        table = Table(
            "json_contains_items",
            mapper_registry.metadata,
            Column("id", Integer, primary_key=True),
            Column("tags", JSON),
        )

        class Item:
            pass

        mapper_registry.map_imperatively(Item, table)

        from arvel.database.query import QueryBuilder

        sql = (
            QueryBuilder[Any](Item)
            .where_json_contains("tags", ["sale"])
            .to_sql(dialect="postgresql")
        )
        assert "tags @>" in sql
        assert "sale" in sql

    def test_query_mixin_exposes_where_json_contains(self) -> None:
        from arvel.database.query_mixin import QueryMixin

        assert hasattr(QueryMixin, "where_json_contains")


# JsonResource helpers


class TestStory12JsonResourceHelpers:
    """when(), when_loaded(), merge_when() on JsonResource."""

    def test_when_excludes_field_when_condition_false(self) -> None:
        from arvel.http.resources import JsonResource

        class MyResource(JsonResource[Any]):
            def to_dict(self, request: Any) -> dict[str, Any]:
                return {
                    "id": self.resource.id,
                    "secret": self.when(False, "admin_secret"),
                }

        resource_obj = MagicMock(id=1)
        res = MyResource(resource_obj)
        result = res.to_dict(request=None)
        assert "secret" not in result

    def test_when_includes_field_when_condition_true(self) -> None:
        from arvel.http.resources import JsonResource

        class MyResource(JsonResource[Any]):
            def to_dict(self, request: Any) -> dict[str, Any]:
                return {
                    "id": self.resource.id,
                    "secret": self.when(True, "admin_secret"),
                }

        resource_obj = MagicMock(id=1)
        res = MyResource(resource_obj)
        result = res.to_dict(request=None)
        assert result["secret"] == "admin_secret"

    def test_when_loaded_excludes_when_relation_not_in_dict(self) -> None:
        from arvel.http.resources import JsonResource

        class MyResource(JsonResource[Any]):
            def to_dict(self, request: Any) -> dict[str, Any]:
                return {
                    "id": self.resource.id,
                    "category": self.when_loaded("category"),
                }

        resource_obj = MagicMock(spec=["id"])
        resource_obj.id = 1
        #'category' not in __dict__ — not loaded
        resource_obj.__dict__ = {"id": 1}
        res = MyResource(resource_obj)
        result = res.to_dict(request=None)
        assert "category" not in result

    def test_when_loaded_includes_when_relation_in_dict(self) -> None:
        from arvel.http.resources import JsonResource

        class CategoryObj:
            name = "Electronics"

        class MyResource(JsonResource[Any]):
            def to_dict(self, request: Any) -> dict[str, Any]:
                return {
                    "id": self.resource.id,
                    "category": self.when_loaded("category"),
                }

        # Use a simple object whose __dict__ we can control directly
        class _FakeProduct:
            pass

        category = CategoryObj()
        resource_obj = _FakeProduct()
        resource_obj.id = 1  # type: ignore[attr-defined]
        resource_obj.category = category  # type: ignore[attr-defined]
        # __dict__ now contains "id" and "category" → when_loaded should find "category"
        res = MyResource(resource_obj)
        result = res.to_dict(request=None)
        assert result["category"] is category

    def test_merge_when_merges_dict_when_condition_true(self) -> None:
        from arvel.http.resources import JsonResource

        class MyResource(JsonResource[Any]):
            def to_dict(self, request: Any) -> dict[str, Any]:
                result: dict[str, Any] = {"id": self.resource.id}
                result.update(self.merge_when(True, {"secret": "val", "debug": True}))
                return result

        resource_obj = MagicMock(id=1)
        res = MyResource(resource_obj)
        result = res.to_dict(request=None)
        assert result["secret"] == "val"
        assert result["debug"] is True

    def test_merge_when_returns_empty_when_condition_false(self) -> None:
        from arvel.http.resources import JsonResource

        class MyResource(JsonResource[Any]):
            def to_dict(self, request: Any) -> dict[str, Any]:
                result: dict[str, Any] = {"id": self.resource.id}
                result.update(self.merge_when(False, {"secret": "val"}))
                return result

        resource_obj = MagicMock(id=1)
        res = MyResource(resource_obj)
        result = res.to_dict(request=None)
        assert "secret" not in result


# Throttle fix


class TestStory14ThrottleFix:
    """Throttle middleware must not wrap raw handler returns in JSONResponse."""

    @pytest.mark.asyncio
    async def test_throttle_does_not_wrap_raw_dict_in_json_response(self) -> None:
        from arvel.http._middleware_core import Throttle
        from starlette.responses import JSONResponse

        throttle = Throttle(max_attempts=10)
        raw_dict = {"items": [1, 2, 3]}

        async def handler(request: Any) -> dict[str, Any]:
            return raw_dict

        response = await throttle.handle(MagicMock(), handler)
        # Must NOT be a JSONResponse — FastAPI should serialize via response_model
        assert not isinstance(response, JSONResponse), (
            "Throttle must not wrap raw returns in JSONResponse"
        )

    @pytest.mark.asyncio
    async def test_throttle_adds_headers_to_response_objects(self) -> None:
        from arvel.http._middleware_core import Throttle
        from starlette.responses import Response

        throttle = Throttle(max_attempts=10)
        raw_response = Response(content=b"ok", status_code=200)

        async def handler(request: Any) -> Response:
            return raw_response

        response = await throttle.handle(MagicMock(), handler)
        assert isinstance(response, Response)
        assert "X-RateLimit-Limit" in response.headers


# Queued notifications


class TestStory16QueuedNotifications:
    """Notification implementing ShouldQueue is dispatched through the queue."""

    @pytest.mark.asyncio
    async def test_notify_queues_when_notification_implements_should_queue(self) -> None:
        from arvel.notifications.notification import Notification
        from arvel.notifications.should_queue import ShouldQueue

        class QueuedNotification(Notification, ShouldQueue):
            def via(self, notifiable: Any) -> list[str]:
                return ["log"]

        queued_spy: list[Any] = []

        manager = MagicMock()
        manager.send = AsyncMock()

        def _capture(_n: Any, notif: Any) -> None:
            queued_spy.append(notif)

        manager.send_via_queue = AsyncMock(side_effect=_capture)

        from arvel.notifications.notifiable import Notifiable

        class User(Notifiable):
            id = 1
            notification_manager = manager

        user = User()
        notif = QueuedNotification()
        await user.notify(notif)

        # ShouldQueue notifications must go via queue (send_via_queue), not inline send
        manager.send_via_queue.assert_called_once()
        manager.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_now_bypasses_queue_for_should_queue_notification(self) -> None:
        from arvel.notifications.notification import Notification
        from arvel.notifications.should_queue import ShouldQueue

        class QueuedNotification(Notification, ShouldQueue):
            def via(self, notifiable: Any) -> list[str]:
                return ["log"]

        manager = MagicMock()
        manager.send = AsyncMock()
        manager.send_now = AsyncMock()
        manager.send_via_queue = AsyncMock()

        from arvel.notifications.notifiable import Notifiable

        class User(Notifiable):
            id = 1
            notification_manager = manager

        user = User()
        notif = QueuedNotification()
        await user.notify_now(notif)

        # notify_now must call send_now (inline bypass), not send_via_queue
        manager.send_now.assert_called_once()
        manager.send_via_queue.assert_not_called()

    def test_should_queue_class_is_importable_from_notifications(self) -> None:
        from arvel.notifications.should_queue import ShouldQueue

        assert ShouldQueue is not None

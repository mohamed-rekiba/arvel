"""Tests for facade `.fake()` helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

import pytest


class TestCacheFake:
    @pytest.mark.asyncio
    async def test_fake_swaps_in_array_store(self) -> None:
        from arvel.facades.cache import Cache
        from arvel.testing.fakes.cache import CacheFakeContext

        with Cache.fake() as ctx:
            assert isinstance(ctx, CacheFakeContext)
            await Cache.put("key", "value", ttl=60)
            assert await Cache.get("key") == "value"

    @pytest.mark.asyncio
    async def test_assert_stored(self) -> None:
        from arvel.facades.cache import Cache

        with Cache.fake():
            await Cache.put("hit", 1, ttl=10)
            Cache.assert_stored("hit")
            with pytest.raises(AssertionError, match="missing"):
                Cache.assert_stored("nope")

    @pytest.mark.asyncio
    async def test_assert_missing(self) -> None:
        from arvel.facades.cache import Cache

        with Cache.fake():
            await Cache.put("hit", 1, ttl=10)
            Cache.assert_missing("nope")
            with pytest.raises(AssertionError):
                Cache.assert_missing("hit")

    def test_assert_helpers_require_fake_cache(self) -> None:
        from arvel.cache import CacheManager
        from arvel.config.cache_config import CacheConfig, CacheDriver
        from arvel.facades.cache import Cache

        previous = Cache.manager
        Cache.manager = CacheManager(CacheConfig(connection=CacheDriver.NULL))
        try:
            with pytest.raises(AssertionError, match="requires Cache.fake"):
                Cache.assert_stored("missing")
            with pytest.raises(AssertionError, match="requires Cache.fake"):
                Cache.assert_missing("missing")
        finally:
            Cache.manager = previous


class TestEventFake:
    @pytest.mark.asyncio
    async def test_fake_records_dispatched_events(self) -> None:
        from arvel.events.event import Event as EventBase
        from arvel.facades.event import Event

        class UserRegistered(EventBase):
            user_id: int

        with Event.fake():
            await Event.dispatch(UserRegistered(user_id=42))
            Event.assert_dispatched(UserRegistered)
            Event.assert_dispatched(UserRegistered, times=1)

    @pytest.mark.asyncio
    async def test_assert_not_dispatched(self) -> None:
        from arvel.events.event import Event as EventBase
        from arvel.facades.event import Event

        class NeverFired(EventBase):
            pass

        with Event.fake():
            Event.assert_not_dispatched(NeverFired)

    def test_assert_dispatched_requires_fake(self) -> None:
        from arvel.events.dispatcher import EventDispatcher
        from arvel.events.event import Event as EventBase
        from arvel.facades.event import Event

        class NeverFired(EventBase):
            pass

        previous = Event.swap_dispatcher(EventDispatcher())
        try:
            with pytest.raises(AssertionError, match="requires Event.fake"):
                Event.assert_dispatched(NeverFired)
        finally:
            Event.swap_dispatcher(previous)

    @pytest.mark.asyncio
    async def test_assert_dispatched_failure_branches(self) -> None:
        from arvel.events.event import Event as EventBase
        from arvel.facades.event import Event

        class UserRegistered(EventBase):
            user_id: int

        class NeverFired(EventBase):
            pass

        with Event.fake():
            with pytest.raises(AssertionError, match="was not dispatched"):
                Event.assert_dispatched(NeverFired)

            await Event.dispatch(UserRegistered(user_id=1))
            with pytest.raises(AssertionError, match="expected 2 dispatches, got 1"):
                Event.assert_dispatched(UserRegistered, times=2)

    def test_assert_not_dispatched_requires_fake(self) -> None:
        from arvel.events.dispatcher import EventDispatcher
        from arvel.events.event import Event as EventBase
        from arvel.facades.event import Event

        class NeverFired(EventBase):
            pass

        previous = Event.swap_dispatcher(EventDispatcher())
        try:
            with pytest.raises(AssertionError, match="requires Event.fake"):
                Event.assert_not_dispatched(NeverFired)
        finally:
            Event.swap_dispatcher(previous)

    @pytest.mark.asyncio
    async def test_assert_not_dispatched_fails_when_event_was_dispatched(self) -> None:
        from arvel.events.event import Event as EventBase
        from arvel.facades.event import Event, EventDispatcherLike

        class UserRegistered(EventBase):
            user_id: int

        with Event.fake():
            await Event.dispatch(UserRegistered(user_id=1))
            with pytest.raises(AssertionError, match="was dispatched 1 time"):
                Event.assert_not_dispatched(UserRegistered)

        dispatch = cast(
            "Callable[[EventDispatcherLike, EventBase], Awaitable[None]]",
            object.__getattribute__(EventDispatcherLike, "dispatch"),
        )
        await dispatch(cast("EventDispatcherLike", object()), UserRegistered(user_id=1))


class TestStorageFake:
    @pytest.mark.asyncio
    async def test_fake_creates_in_memory_disk(self) -> None:
        from arvel.facades.storage import Storage

        with Storage.fake():
            await Storage.disk().put("avatars/me.png", b"png-bytes")
            Storage.assert_exists("avatars/me.png")
            Storage.assert_missing("does/not/exist.png")

    def test_disk_not_bound_raises(self) -> None:
        from arvel.cache.exceptions import FacadeNotBoundError
        from arvel.facades.storage import Storage

        previous = Storage.swap_manager(None)
        try:
            with pytest.raises(FacadeNotBoundError, match="Storage"):
                Storage.disk()
        finally:
            Storage.swap_manager(previous)

    def test_assert_exists_requires_fake(self) -> None:
        from arvel.facades.storage import Storage, StorageManagerLike

        previous = Storage.swap_manager(cast("StorageManagerLike", object()))
        try:
            with pytest.raises(AssertionError, match="requires Storage.fake"):
                Storage.assert_exists("avatars/me.png")
        finally:
            Storage.swap_manager(previous)

    def test_assert_exists_fails_when_path_is_missing(self) -> None:
        from arvel.facades.storage import Storage

        with Storage.fake(), pytest.raises(AssertionError, match="does not exist"):
            Storage.assert_exists("avatars/missing.png")

    def test_assert_missing_requires_fake(self) -> None:
        from arvel.facades.storage import Storage, StorageManagerLike

        previous = Storage.swap_manager(cast("StorageManagerLike", object()))
        try:
            with pytest.raises(AssertionError, match="requires Storage.fake"):
                Storage.assert_missing("avatars/me.png")
        finally:
            Storage.swap_manager(previous)

    @pytest.mark.asyncio
    async def test_assert_missing_fails_when_path_exists(self) -> None:
        from arvel.facades.storage import Storage

        with Storage.fake():
            await Storage.disk().put("avatars/me.png", b"png-bytes")
            with pytest.raises(AssertionError, match="exists but should be missing"):
                Storage.assert_missing("avatars/me.png")

    def test_storage_manager_protocol_stub_is_callable(self) -> None:
        from arvel.facades.storage import StorageManagerLike

        disk = cast(
            "Callable[[StorageManagerLike], object]",
            object.__getattribute__(StorageManagerLike, "disk"),
        )
        assert disk(cast("StorageManagerLike", object())) is None


class TestNotificationFake:
    @pytest.mark.asyncio
    async def test_fake_records_sent_notifications(self) -> None:
        from arvel.facades.notification import Notification
        from arvel.notifications.notification import Notification as _Notification

        class WelcomeEmail(_Notification):
            def via(self, notifiable: object) -> list[str]:
                return ["log"]

        class _User:
            id = 42

        user = _User()

        with Notification.fake() as ctx:
            await Notification.send(user, WelcomeEmail())
            await Notification.send_now(user, WelcomeEmail())
            assert len(ctx.fake.sent) == 2
            Notification.assert_sent_to(user, WelcomeEmail)
            Notification.assert_sent_to(user, WelcomeEmail, times=2)

    @pytest.mark.asyncio
    async def test_assert_failures(self) -> None:
        from arvel.facades.notification import Notification
        from arvel.notifications.notification import Notification as _Notification

        class WelcomeEmail(_Notification):
            def via(self, notifiable: object) -> list[str]:
                return ["log"]

        class OtherEmail(_Notification):
            def via(self, notifiable: object) -> list[str]:
                return ["log"]

        class _User:
            id = 1

        user = _User()

        with Notification.fake():
            with pytest.raises(AssertionError, match="was not sent"):
                Notification.assert_sent_to(user, WelcomeEmail)

            Notification.assert_nothing_sent()

            await Notification.send(user, WelcomeEmail())
            Notification.assert_not_sent_to(user, OtherEmail)

            with pytest.raises(AssertionError, match="was sent to"):
                Notification.assert_not_sent_to(user, WelcomeEmail)
            with pytest.raises(AssertionError, match="expected 5, got 1"):
                Notification.assert_sent_to(user, WelcomeEmail, times=5)
            with pytest.raises(AssertionError, match="1 notification"):
                Notification.assert_nothing_sent()

    def test_asserts_require_fake_context(self) -> None:
        from arvel.facades.notification import Notification
        from arvel.notifications.notification import Notification as _Notification

        class _Boom(_Notification):
            def via(self, notifiable: object) -> list[str]:
                return ["log"]

        Notification.reset()
        # No manager bound at all — asserts should still fail with the same message.
        with pytest.raises(TypeError, match="requires Notification.fake"):
            Notification.assert_sent_to(object(), _Boom)
        with pytest.raises(TypeError, match="requires Notification.fake"):
            Notification.assert_not_sent_to(object(), _Boom)
        with pytest.raises(TypeError, match="requires Notification.fake"):
            Notification.assert_nothing_sent()


class TestSessionFacade:
    def test_manager_not_bound_raises(self) -> None:
        from arvel.cache.exceptions import FacadeNotBoundError
        from arvel.facades.session import Session

        previous = type.__getattribute__(Session, "_manager")
        type.__setattr__(Session, "_manager", None)
        try:
            with pytest.raises(FacadeNotBoundError, match="Session"):
                Session.manager()
        finally:
            type.__setattr__(Session, "_manager", previous)

    def test_manager_returns_bound_manager(self) -> None:
        from arvel.config.session_config import SessionConfig, SessionDriver
        from arvel.container import Container
        from arvel.facades.session import Session
        from arvel.session import SessionManager

        container = Container()
        manager = SessionManager(SessionConfig(driver=SessionDriver.FILE))
        container.instance(SessionManager, manager)

        previous = type.__getattribute__(Session, "_manager")
        try:
            Session.bind(container)
            assert Session.manager() is manager
        finally:
            type.__setattr__(Session, "_manager", previous)

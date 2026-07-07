"""Coverage-closing behavioral tests for the thin service providers' `register()`/`boot()`
factory bodies: search, queue (including the `queue_dispatcher`/`broadcast_dispatcher` rail
callables), media, features, and notifications. Each asserts the bound service actually
resolves to the right type (or actually enqueues), not just that `register()` didn't raise."""

from __future__ import annotations

from typing import Any

from arvel.features import FeatureManager
from arvel.features.provider import FeatureServiceProvider
from arvel.kernel import Application
from arvel.media import ImageManager, VideoManager
from arvel.media.provider import MediaServiceProvider
from arvel.notifications import NotificationManager
from arvel.notifications.provider import NotificationServiceProvider
from arvel.queue import Job, QueueManager
from arvel.queue.provider import QueueServiceProvider
from arvel.search import SearchManager
from arvel.search.provider import SearchServiceProvider


def test_search_provider_binds_a_resolvable_search_manager() -> None:
    app = Application()
    SearchServiceProvider(app).register()
    assert isinstance(app.make("search"), SearchManager)


def test_search_provider_boot_registers_the_queue_listener_when_configured() -> None:
    from arvel.events import Dispatcher
    from arvel.kernel import set_application
    from arvel.search import ModelIndexRequested
    from arvel.search.listeners import handle_index_request

    app = Application()
    set_application(app)  # SearchSettings() reads config() off the global app
    try:
        app.make("config").set("search", {"queue": True})
        app.instance("events", Dispatcher(app))
        SearchServiceProvider(app).register()
        SearchServiceProvider(app).boot()

        dispatcher = app.make("events")
        assert dispatcher.has_listeners(ModelIndexRequested)
        assert handle_index_request in dispatcher._listeners[ModelIndexRequested]
    finally:
        set_application(None)


def test_search_provider_boot_is_a_noop_without_events_bound() -> None:
    app = Application()
    SearchServiceProvider(app).register()
    SearchServiceProvider(app).boot()  # events not bound: returns early, no crash


def test_media_provider_binds_resolvable_image_and_video_managers() -> None:
    app = Application()
    MediaServiceProvider(app).register()
    assert isinstance(app.make("image"), ImageManager)
    assert isinstance(app.make("video"), VideoManager)


def test_features_provider_binds_a_resolvable_feature_manager() -> None:
    app = Application()
    FeatureServiceProvider(app).register()
    assert isinstance(app.make("features"), FeatureManager)


def test_notifications_provider_binds_a_resolvable_notification_manager() -> None:
    app = Application()
    NotificationServiceProvider(app).register()
    assert isinstance(app.make("notifications"), NotificationManager)


async def test_queue_provider_binds_queue_schedule_and_dispatcher_rails() -> None:
    from arvel.queue.scheduler import Schedule

    app = Application()
    QueueServiceProvider(app).register()

    assert isinstance(app.make("queue"), QueueManager)  # make_queue factory body
    assert isinstance(app.make("schedule"), Schedule)  # make_schedule, no cache bound

    pushed: list[Any] = []
    real_push = QueueManager.push_instance

    async def fake_push_instance(self: QueueManager, job: Job, *, queue: str | None = None) -> Any:
        pushed.append(job)
        return "queued"

    app.make("queue").push_instance = fake_push_instance.__get__(app.make("queue"))  # type: ignore[method-assign]

    class _RecordedListener:
        def handle(self, *args: Any) -> None:
            raise AssertionError("must run on the worker, not inline")

    dispatch_listener = app.make("queue_dispatcher")
    result = await dispatch_listener(_RecordedListener(), ())
    assert result == "queued"
    assert len(pushed) == 1  # a CallQueuedListener job was pushed, not run inline

    class _Ev:
        pass

    dispatch_broadcast = app.make("broadcast_dispatcher")
    result2 = await dispatch_broadcast(_Ev())
    assert result2 == "queued"
    assert len(pushed) == 2  # a CallQueuedBroadcast job was pushed
    assert real_push  # keep a reference so nothing gets optimized away


async def test_queue_provider_schedule_threads_a_bound_cache() -> None:
    from arvel.cache import CacheManager

    app = Application()
    app.singleton("cache", lambda _app: CacheManager().driver())
    QueueServiceProvider(app).register()
    schedule = app.make("schedule")
    assert schedule._cache is not None  # cache bound: threaded into Schedule

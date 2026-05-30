"""Service providers for the e-commerce demo."""

from __future__ import annotations

from app.providers.app_service_provider import AppServiceProvider
from arvel.auth.provider import AuthServiceProvider
from arvel.events.providers.event_service_provider import EventServiceProvider
from arvel.mail.providers.mail_service_provider import MailServiceProvider
from arvel.providers import BroadcastServiceProvider, ServiceProvider
from arvel.providers.cache_provider import CacheServiceProvider
from arvel.providers.scheduler_provider import SchedulerServiceProvider
from arvel.providers.storage_provider import StorageServiceProvider
from arvel.queue.providers.queue_service_provider import QueueServiceProvider
from arvel_image import ImageServiceProvider

providers: list[type[ServiceProvider]] = [
    CacheServiceProvider,
    SchedulerServiceProvider,
    EventServiceProvider,
    QueueServiceProvider,
    BroadcastServiceProvider,
    StorageServiceProvider,
    ImageServiceProvider,
    MailServiceProvider,
    AuthServiceProvider,
    AppServiceProvider,
]

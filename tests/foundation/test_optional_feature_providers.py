"""Provider wiring tests for queue, security, and media module defaults."""

from __future__ import annotations

import pytest

from arvel.foundation.container import ContainerBuilder, Scope
from arvel.media.config import MediaSettings
from arvel.media.contracts import MediaContract
from arvel.queue.contracts import QueueContract
from arvel.security.contracts import HasherContract


class TestQueueProvider:
    async def test_registers_queue_contract(self, clean_env: None) -> None:
        from arvel.queue.provider import QueueProvider

        builder = ContainerBuilder()
        provider = QueueProvider()
        await provider.register(builder)
        container = builder.build()
        queue = await container.resolve(QueueContract)
        assert isinstance(queue, QueueContract)

    async def test_default_queue_driver_is_sync(self, clean_env: None) -> None:
        from arvel.queue.drivers.sync_driver import SyncQueue
        from arvel.queue.provider import QueueProvider

        builder = ContainerBuilder()
        provider = QueueProvider()
        await provider.register(builder)
        container = builder.build()
        queue = await container.resolve(QueueContract)
        assert isinstance(queue, SyncQueue)

    async def test_taskiq_driver_selected_when_available(
        self, monkeypatch, clean_env: None
    ) -> None:
        pytest.importorskip("taskiq")
        pytest.importorskip("taskiq_redis")
        from arvel.queue.drivers.taskiq_driver import TaskiqQueue
        from arvel.queue.provider import QueueProvider

        monkeypatch.setenv("QUEUE_DRIVER", "taskiq")
        monkeypatch.setenv("QUEUE_TASKIQ_BROKER", "memory")

        builder = ContainerBuilder()
        provider = QueueProvider()
        await provider.register(builder)
        container = builder.build()
        queue = await container.resolve(QueueContract)
        assert isinstance(queue, TaskiqQueue)


class TestSecurityProvider:
    async def test_registers_hasher_contract(self, clean_env: None) -> None:
        from arvel.security.provider import SecurityProvider

        builder = ContainerBuilder()
        provider = SecurityProvider()
        await provider.register(builder)
        container = builder.build()
        hasher = await container.resolve(HasherContract)
        assert isinstance(hasher, HasherContract)

    async def test_respects_hash_driver_settings(self, monkeypatch, clean_env: None) -> None:
        from arvel.security.hashing import Argon2Hasher
        from arvel.security.provider import SecurityProvider

        monkeypatch.setenv("SECURITY_HASH_DRIVER", "argon2")

        builder = ContainerBuilder()
        provider = SecurityProvider()
        await provider.register(builder)
        container = builder.build()
        hasher = await container.resolve(HasherContract)
        assert isinstance(hasher, Argon2Hasher)


class TestMediaProvider:
    async def test_registers_media_contract(self, clean_env: None) -> None:
        from arvel.infra.provider import InfrastructureProvider
        from arvel.media.provider import MediaProvider

        builder = ContainerBuilder()
        infra_provider = InfrastructureProvider()
        media_provider = MediaProvider()
        builder.provide_value(MediaSettings, MediaSettings(), scope=Scope.APP)
        await infra_provider.register(builder)
        await media_provider.register(builder)
        container = builder.build()
        media = await container.resolve(MediaContract)
        assert isinstance(media, MediaContract)

    async def test_media_manager_adds_and_fetches_items(self, clean_env: None) -> None:
        from arvel.infra.provider import InfrastructureProvider
        from arvel.media.provider import MediaProvider

        builder = ContainerBuilder()
        infra_provider = InfrastructureProvider()
        media_provider = MediaProvider()
        builder.provide_value(MediaSettings, MediaSettings(), scope=Scope.APP)
        await infra_provider.register(builder)
        await media_provider.register(builder)
        container = builder.build()
        media = await container.resolve(MediaContract)

        created = await media.add(
            {"type": "User", "id": 1},
            b"image-bytes",
            "avatar.png",
            collection="avatars",
            content_type="image/png",
        )
        items = await media.get_media({"type": "User", "id": 1}, "avatars")

        assert created.id is not None
        assert len(items) == 1

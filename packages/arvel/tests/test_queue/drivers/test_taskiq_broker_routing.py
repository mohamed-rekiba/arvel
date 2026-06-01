"""Unit tests for TaskiqConnection broker selection by URL scheme.

No real broker — only URL parsing and ImportError paths.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest
from arvel.queue.config import TaskiqQueueConfig
from arvel.queue.drivers.taskiq import TaskiqConnection, select_broker_module
from arvel.queue.envelope import JobEnvelope
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# — TaskiqQueueConfig drops result_backend_url
# ---------------------------------------------------------------------------


class TestTaskiqQueueConfigForbidsResultBackend:
    """result_backend_url field is removed entirely."""

    def test_default_broker_url_present(self) -> None:
        cfg = TaskiqQueueConfig()
        assert hasattr(cfg, "broker_url")

    def test_no_result_backend_url_attribute(self) -> None:
        cfg = TaskiqQueueConfig()
        assert not hasattr(cfg, "result_backend_url")

    def test_passing_result_backend_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskiqQueueConfig(result_backend_url="redis://localhost:6379/1")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# — URL-scheme autodetection
# ---------------------------------------------------------------------------


class TestSelectBrokerModule:
    """broker_url scheme picks the right Taskiq broker module."""

    def test_redis_scheme_picks_taskiq_redis(self) -> None:
        module, extra = select_broker_module("redis://localhost:6379/0")
        assert module == "taskiq_redis"
        assert extra == "queue-redis"

    def test_rediss_scheme_picks_taskiq_redis(self) -> None:
        module, _ = select_broker_module("rediss://localhost:6379/0")
        assert module == "taskiq_redis"

    def test_unix_scheme_picks_taskiq_redis(self) -> None:
        module, _ = select_broker_module("unix:///tmp/redis.sock")
        assert module == "taskiq_redis"

    def test_amqp_scheme_picks_taskiq_aio_pika(self) -> None:
        module, extra = select_broker_module("amqp://guest:guest@localhost:5672/")
        assert module == "taskiq_aio_pika"
        assert extra == "queue-amqp"

    def test_amqps_scheme_picks_taskiq_aio_pika(self) -> None:
        module, _ = select_broker_module("amqps://guest:guest@localhost:5671/")
        assert module == "taskiq_aio_pika"

    def test_unknown_scheme_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match=r"kafka"):
            select_broker_module("kafka://localhost:9092/")

    def test_empty_scheme_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            select_broker_module("not-a-url")


# ---------------------------------------------------------------------------
# — Per-scheme ImportError with install command
# ---------------------------------------------------------------------------


@pytest.fixture
def hide_taskiq_redis() -> Iterator[None]:
    """Make `import taskiq_redis` raise ImportError for the duration of one test."""
    saved = sys.modules.get("taskiq_redis")
    sys.modules["taskiq_redis"] = None  # type: ignore[assignment]
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("taskiq_redis", None)
        else:
            sys.modules["taskiq_redis"] = saved


@pytest.fixture
def hide_taskiq_aio_pika() -> Iterator[None]:
    """Make `import taskiq_aio_pika` raise ImportError for the duration of one test."""
    saved = sys.modules.get("taskiq_aio_pika")
    sys.modules["taskiq_aio_pika"] = None  # type: ignore[assignment]
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("taskiq_aio_pika", None)
        else:
            sys.modules["taskiq_aio_pika"] = saved


class TestImportErrorMessages:
    """+ : ImportError mentions the missing extra by exact name."""

    @pytest.mark.usefixtures("hide_taskiq_redis")
    @pytest.mark.asyncio
    async def test_missing_taskiq_redis_message_names_queue_redis_extra(self) -> None:
        cfg = TaskiqQueueConfig(broker_url="redis://localhost:6379/0")
        driver = TaskiqConnection(cfg)
        envelope = JobEnvelope(job_class="tests.dummy.Job", payload={})
        with pytest.raises(ImportError, match=r"arvel\[queue-redis\]") as exc_info:
            await driver.push(envelope)
        # : message must not leak Python internals (no "/site-packages/")
        assert "/site-packages/" not in str(exc_info.value)
        assert "Traceback" not in str(exc_info.value)

    @pytest.mark.usefixtures("hide_taskiq_aio_pika")
    @pytest.mark.asyncio
    async def test_missing_taskiq_aio_pika_message_names_queue_amqp_extra(self) -> None:
        cfg = TaskiqQueueConfig(broker_url="amqp://guest:guest@localhost:5672/")
        driver = TaskiqConnection(cfg)
        envelope = JobEnvelope(job_class="tests.dummy.Job", payload={})
        with pytest.raises(ImportError, match=r"arvel\[queue-amqp\]") as exc_info:
            await driver.push(envelope)
        assert "/site-packages/" not in str(exc_info.value)
        assert "Traceback" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# : AMQP delay-plugin actionable error
# ---------------------------------------------------------------------------


class TestAmqpDelayPluginHint:
    """When AMQP rejects a delayed job with the plugin-missing error, surface
    an arvel-friendly RuntimeError that names the install command."""

    @pytest.mark.asyncio
    async def test_kick_wraps_plugin_missing_error_into_runtimeerror(self) -> None:
        from arvel.queue.envelope import JobEnvelope

        cfg = TaskiqQueueConfig(broker_url="amqp://guest:guest@localhost:5672/")
        driver = TaskiqConnection(cfg)
        envelope = JobEnvelope(job_class="tests.dummy.Job", payload={}, delay=10)

        class _FakeBroker:
            async def startup(self) -> None:
                return None

            async def kick(self, message: object) -> None:
                raise RuntimeError(
                    "Delay requested but no delay queue or delayed-message-exchange "
                    "is configured in the broker."
                )

            async def listen(self) -> object:
                return None

            async def shutdown(self) -> None:
                return None

        # Inject a fake broker bypassing the lazy import + startup path.
        driver._broker = _FakeBroker()  # pyright: ignore[reportPrivateUsage]
        driver._started = True  # pyright: ignore[reportPrivateUsage]

        with pytest.raises(RuntimeError, match=r"rabbitmq-plugins enable") as exc_info:
            await driver.push(envelope)
        assert "rabbitmq_delayed_message_exchange" in str(exc_info.value)
        # Original cause is preserved
        assert exc_info.value.__cause__ is not None

    @pytest.mark.asyncio
    async def test_unrelated_errors_pass_through_unwrapped(self) -> None:
        from arvel.queue.envelope import JobEnvelope

        cfg = TaskiqQueueConfig(broker_url="amqp://guest:guest@localhost:5672/")
        driver = TaskiqConnection(cfg)
        envelope = JobEnvelope(job_class="tests.dummy.Job", payload={}, delay=10)

        class _FakeBroker:
            async def startup(self) -> None:
                return None

            async def kick(self, message: object) -> None:
                raise ConnectionError("broker unreachable")

            async def listen(self) -> object:
                return None

            async def shutdown(self) -> None:
                return None

        driver._broker = _FakeBroker()  # pyright: ignore[reportPrivateUsage]
        driver._started = True  # pyright: ignore[reportPrivateUsage]

        with pytest.raises(ConnectionError, match=r"broker unreachable"):
            await driver.push(envelope)

    @pytest.mark.asyncio
    async def test_no_wrap_when_delay_is_zero(self) -> None:
        """Even if the broker raises the delay-exchange error spuriously on a
        delay-0 job, we must not invent a hint that doesn't apply."""
        from arvel.queue.envelope import JobEnvelope

        cfg = TaskiqQueueConfig(broker_url="amqp://guest:guest@localhost:5672/")
        driver = TaskiqConnection(cfg)
        envelope = JobEnvelope(job_class="tests.dummy.Job", payload={}, delay=0)

        class _FakeBroker:
            async def startup(self) -> None:
                return None

            async def kick(self, message: object) -> None:
                raise RuntimeError("Delay requested but no delay queue configured")

            async def listen(self) -> object:
                return None

            async def shutdown(self) -> None:
                return None

        driver._broker = _FakeBroker()  # pyright: ignore[reportPrivateUsage]
        driver._started = True  # pyright: ignore[reportPrivateUsage]

        with pytest.raises(RuntimeError) as exc_info:
            await driver.push(envelope)
        # Original message passes through, no rabbitmq-plugins hint added
        assert "rabbitmq-plugins" not in str(exc_info.value)

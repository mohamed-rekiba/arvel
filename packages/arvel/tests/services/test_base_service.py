"""Epic 001 Story 4 — BaseService lifecycle contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.application import Application
from arvel.application.errors import BootError, ServiceConnectError
from arvel.services import BaseService, HealthResult, HealthStatus


class _RecordingService(BaseService):
    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self._log = log

    async def connect(self) -> None:
        self._log.append(f"connect:{self.name}")

    async def disconnect(self) -> None:
        self._log.append(f"disconnect:{self.name}")

    async def health_check(self) -> HealthResult:
        return HealthResult(HealthStatus.healthy)


def _app(tmp_path: Path) -> Application:
    return Application.configure(tmp_path).with_environment("testing").with_providers([]).create()


async def test_connect_on_boot_disconnect_reverse_on_shutdown(tmp_path: Path) -> None:
    log: list[str] = []
    app = _app(tmp_path)
    app.register_service(_RecordingService("a", log))
    app.register_service(_RecordingService("b", log))

    await app.boot()
    await app.shutdown()

    assert log == ["connect:a", "connect:b", "disconnect:b", "disconnect:a"]


async def test_health_check_healthy(tmp_path: Path) -> None:
    service = _RecordingService("a", [])
    result = await service.health_check()
    assert result.status is HealthStatus.healthy


async def test_connect_failure_raises_boot_error_with_name(tmp_path: Path) -> None:
    class _Boom(BaseService):
        name = "boom"

        async def connect(self) -> None:
            raise RuntimeError("no socket")

        async def health_check(self) -> HealthResult:
            return HealthResult(HealthStatus.healthy)

    app = _app(tmp_path)
    app.register_service(_Boom())

    with pytest.raises(BootError) as excinfo:
        await app.boot()

    assert isinstance(excinfo.value, ServiceConnectError)
    assert "boom" in str(excinfo.value)


async def test_disconnect_failure_is_isolated(tmp_path: Path) -> None:
    log: list[str] = []

    class _BadDisconnect(BaseService):
        name = "bad"

        async def disconnect(self) -> None:
            raise RuntimeError("flush failed")

        async def health_check(self) -> HealthResult:
            return HealthResult(HealthStatus.healthy)

    app = _app(tmp_path)
    app.register_service(_BadDisconnect())
    app.register_service(_RecordingService("good", log))

    await app.boot()
    await app.shutdown()  # must not raise

    # The good service still disconnected even though "bad" raised first (reverse order).
    assert "disconnect:good" in log

"""Epic 001 Story 7 — graceful shutdown and OS signal handling."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.application import Application
from arvel.console.commands.serve import ServeCommand
from arvel.services import BaseService, HealthResult, HealthStatus


class _Recorder(BaseService):
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


async def test_shutdown_disconnects_in_reverse_order(tmp_path: Path) -> None:
    log: list[str] = []
    app = _app(tmp_path)
    app.register_service(_Recorder("a", log))
    app.register_service(_Recorder("b", log))

    await app.boot()
    await app.shutdown()

    assert log == ["connect:a", "connect:b", "disconnect:b", "disconnect:a"]


async def test_failing_disconnect_does_not_strand_others(tmp_path: Path) -> None:
    log: list[str] = []

    class _Boom(BaseService):
        name = "boom"

        async def disconnect(self) -> None:
            raise RuntimeError("disconnect failed")

        async def health_check(self) -> HealthResult:
            return HealthResult(HealthStatus.healthy)

    app = _app(tmp_path)
    app.register_service(_Recorder("a", log))
    app.register_service(_Boom())

    await app.boot()
    await app.shutdown()  # must not raise

    assert "disconnect:a" in log


def _capture_uvicorn(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    def _fake_run(app: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("arvel.console.commands.serve.uvicorn.run", _fake_run)
    return captured


def test_serve_passes_graceful_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRACEFUL_SHUTDOWN_TIMEOUT", "30")
    captured = _capture_uvicorn(monkeypatch)

    ServeCommand().serve(host="127.0.0.1", port=8000, reload=False)

    assert captured["timeout_graceful_shutdown"] == 30


def test_serve_timeout_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRACEFUL_SHUTDOWN_TIMEOUT", raising=False)
    captured = _capture_uvicorn(monkeypatch)

    ServeCommand().serve(host="127.0.0.1", port=8000, reload=False)

    assert captured["timeout_graceful_shutdown"] is None


def test_serve_timeout_none_when_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRACEFUL_SHUTDOWN_TIMEOUT", "abc")
    captured = _capture_uvicorn(monkeypatch)

    ServeCommand().serve(host="127.0.0.1", port=8000, reload=False)

    assert captured["timeout_graceful_shutdown"] is None

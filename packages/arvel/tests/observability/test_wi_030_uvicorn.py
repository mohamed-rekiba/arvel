"""Uvicorn log capture."""

from __future__ import annotations

import logging

import pytest


class TestUvicornBridgeImport:
    def test_uvicorn_bridge_importable(self) -> None:
        from arvel.observability.uvicorn_bridge import install_uvicorn_bridge

        _ = install_uvicorn_bridge


class TestUvicornLoggerSilenced:
    def test_uvicorn_access_handler_cleared_after_install(self) -> None:
        from arvel.observability.uvicorn_bridge import install_uvicorn_bridge

        install_uvicorn_bridge()
        uvicorn_logger = logging.getLogger("uvicorn.access")
        # After bridging, the original uvicorn handler must be gone
        assert not any(
            type(h).__name__ == "StreamHandler" and not getattr(h, "_otel_bridge", None)
            for h in uvicorn_logger.handlers
        ), "Uvicorn access logger still has its original StreamHandler"

    def test_uvicorn_error_handler_cleared_after_install(self) -> None:
        from arvel.observability.uvicorn_bridge import install_uvicorn_bridge

        install_uvicorn_bridge()
        uvicorn_logger = logging.getLogger("uvicorn.error")
        assert not any(
            type(h).__name__ == "StreamHandler" and not getattr(h, "_otel_bridge", None)
            for h in uvicorn_logger.handlers
        )

    def test_no_duplicate_output_after_install(self) -> None:
        from arvel.observability.uvicorn_bridge import install_uvicorn_bridge
        from arvel.testing.observability import FakeObservability

        install_uvicorn_bridge()

        # Emitting on the uvicorn.access logger should produce OTel records, not stdout
        with FakeObservability() as obs:
            uvicorn_access = logging.getLogger("uvicorn.access")
            uvicorn_access.info('127.0.0.1 - - "GET /ping HTTP/1.1" 200')

        # The record should have arrived in OTel (via bridge), not been lost
        assert len(obs.log_records) >= 1


class TestUvicornAccessLogDisable:
    def test_uvicorn_access_forwarding_can_be_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_UVICORN_ACCESS", "false")
        from arvel.observability.uvicorn_bridge import install_uvicorn_bridge
        from arvel.testing.observability import FakeObservability

        install_uvicorn_bridge()

        with FakeObservability() as obs:
            logging.getLogger("uvicorn.access").info("GET /ping 200")

        access_records = [
            r for r in obs.log_records if "uvicorn.access" in (r.instrumentation_scope.name or "")
        ]
        assert not access_records, (
            "uvicorn.access records emitted even though LOG_UVICORN_ACCESS=false"
        )

"""Observability provider small branches."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import pytest
from arvel.observability import provider as provider_module
from arvel.observability.config import ObservabilityConfig
from arvel.observability.provider import ObservabilityServiceProvider

if TYPE_CHECKING:
    from arvel.application import Application


class _Container:
    def __init__(self) -> None:
        self.value: ObservabilityConfig | None = None

    def bound(self, key: type[ObservabilityConfig]) -> bool:
        assert key is ObservabilityConfig
        return self.value is not None

    def instance(self, key: type[ObservabilityConfig], value: ObservabilityConfig) -> None:
        assert key is ObservabilityConfig
        self.value = value

    def make(self, key: type[ObservabilityConfig]) -> ObservabilityConfig:
        assert key is ObservabilityConfig
        if self.value is None:
            raise LookupError("missing config")
        return self.value


class _App:
    def __init__(self, container: _Container) -> None:
        self.container = container


def _provider_with_container(container: _Container) -> ObservabilityServiceProvider:
    return ObservabilityServiceProvider(cast("Application", _App(container)))


def test_parse_headers_skips_empty_and_malformed_pairs() -> None:
    parse_headers = cast(
        "Callable[[str], dict[str, str]]",
        object.__getattribute__(
            __import__("arvel.observability.provider", fromlist=["_parse_headers"]),
            "_parse_headers",
        ),
    )

    assert parse_headers("") == {}
    assert parse_headers("a=1, broken, b = two ") == {"a": "1", "b": "two"}


def test_boot_providers_returns_when_sdk_is_disabled() -> None:
    provider = object.__new__(ObservabilityServiceProvider)

    provider.boot_providers(ObservabilityConfig.model_validate({"OTEL_SDK_DISABLED": True}))


async def test_register_and_boot_use_container_config(monkeypatch: pytest.MonkeyPatch) -> None:
    container = _Container()
    provider = _provider_with_container(container)
    calls: list[ObservabilityConfig] = []

    monkeypatch.setattr(provider, "boot_providers", calls.append)

    provider.register()
    assert container.value is not None
    await provider.boot()
    assert calls == [container.value]


def test_bootstrap_otel_wires_providers_without_optional_instrumentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    bootstrap = cast(
        "Callable[[ObservabilityConfig], None]",
        object.__getattribute__(provider_module, "_bootstrap_otel"),
    )

    def attach_trace(provider: object, config: ObservabilityConfig) -> None:
        calls.append(f"trace:{config.service_name}")

    def attach_logs(provider: object, config: ObservabilityConfig) -> None:
        calls.append(f"logs:{config.service_name}")

    def bootstrap_metrics(config: ObservabilityConfig, resource: object) -> None:
        calls.append(f"metrics:{config.service_name}")

    monkeypatch.setattr(provider_module, "_attach_trace_exporters", attach_trace)
    monkeypatch.setattr(provider_module, "_attach_log_processors", attach_logs)
    monkeypatch.setattr(provider_module, "_bootstrap_metrics", bootstrap_metrics)
    monkeypatch.setattr(
        "arvel.observability.uvicorn_bridge.install_uvicorn_bridge",
        lambda: calls.append("bridge"),
    )

    bootstrap(
        ObservabilityConfig.model_validate(
            {"OTEL_SERVICE_NAME": "tests", "DB_QUERY_LOG_ENABLED": False}
        )
    )

    assert calls == ["trace:tests", "logs:tests", "metrics:tests", "bridge"]

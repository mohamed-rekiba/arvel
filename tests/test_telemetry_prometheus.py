"""Prometheus pull mode: a PrometheusMetricReader exposes OTel metrics, and TelemetryServiceProvider
registers a /metrics scrape route that returns them in the Prometheus exposition format."""

from __future__ import annotations

from typing import Any

from arvel.http.response import prometheus_metrics  # handler lives in http (DR-0026)
from arvel.telemetry import TelemetrySettings, _build_metric_reader


def test_prometheus_reader_selected_when_enabled() -> None:
    from opentelemetry.exporter.prometheus import PrometheusMetricReader

    settings = TelemetrySettings()
    settings.prometheus = True
    assert isinstance(_build_metric_reader(settings), PrometheusMetricReader)


async def test_metrics_handler_returns_prometheus_exposition() -> None:
    response = await prometheus_metrics()
    assert response.headers["content-type"].startswith("text/plain")
    body = response.content.decode() if isinstance(response.content, bytes) else response.content
    assert "# HELP" in body or "# TYPE" in body or body == ""  # valid exposition (possibly empty)


def test_provider_registers_metrics_route_when_prometheus_on() -> None:
    # telemetry must not import arvel.http (DR-0026); the routing provider wires /metrics instead.
    from arvel.kernel import Application, set_application
    from arvel.routing import Router
    from arvel.routing.provider import RoutingServiceProvider

    app = Application()
    app.instance("router", Router())
    app.make("config").set("telemetry", {"enabled": True, "prometheus": True})
    set_application(app)
    try:
        RoutingServiceProvider(app).register()
        router: Any = app.make("router")
        paths = [definition.path for definition in router._routes]
        assert "/metrics" in paths
    finally:
        set_application(None)


def test_provider_skips_metrics_route_when_prometheus_off() -> None:
    from arvel.kernel import Application, set_application
    from arvel.routing import Router
    from arvel.routing.provider import RoutingServiceProvider

    app = Application()
    app.instance("router", Router())
    app.make("config").set("telemetry", {"enabled": True, "prometheus": False})
    set_application(app)
    try:
        RoutingServiceProvider(app).register()
        router: Any = app.make("router")
        assert "/metrics" not in [definition.path for definition in router._routes]
    finally:
        set_application(None)

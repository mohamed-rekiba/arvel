"""TelemetryServiceProvider — wires OpenTelemetry tracing at boot when ``telemetry.enabled``.

Auto-discovered via the ``arvel.providers`` entry point. ``boot()`` calls :func:`arvel.telemetry.configure`,
which is a no-op unless telemetry is turned on in config — so a default app pays nothing (opentelemetry
is never imported), and an opted-in app exports traces to its configured OTLP backend.
"""

from __future__ import annotations

from arvel.kernel.service_provider import ServiceProvider


class TelemetryServiceProvider(ServiceProvider):
    def register(self) -> None:
        """Expose the Prometheus scrape endpoint when configured. Registered here (not boot) so it lands
        in the router before it's compiled into the served app (Application.as_asgi → router.apply_to)."""
        from arvel.telemetry import TelemetrySettings

        if TelemetrySettings().prometheus and self.app.bound("router"):
            from arvel.telemetry import prometheus_metrics

            self.app.make("router").get("/metrics", prometheus_metrics, name="telemetry.metrics")

    def boot(self) -> None:
        from arvel.telemetry import configure

        configure()  # no-op unless telemetry.enabled (lazy: imports opentelemetry only when on)

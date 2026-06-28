"""TelemetryServiceProvider — wires OpenTelemetry tracing at boot when ``telemetry.enabled``.

Auto-discovered via the ``arvel.providers`` entry point. ``boot()`` calls :func:`arvel.telemetry.configure`,
which is a no-op unless telemetry is turned on in config — so a default app pays nothing (opentelemetry
is never imported), and an opted-in app exports traces to its configured OTLP backend.
"""

from __future__ import annotations

from arvel.kernel.service_provider import ServiceProvider


class TelemetryServiceProvider(ServiceProvider):
    def register(self) -> None:
        """No bindings — telemetry is global OTel state set up in boot()."""

    def boot(self) -> None:
        from arvel.telemetry import configure

        configure()  # no-op unless telemetry.enabled (lazy: imports opentelemetry only when on)

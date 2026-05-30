"""Declared service providers for this application.

The framework registers its own baseline providers automatically (Config, Log,
Lang, Database, Http, Scheduler, Console). List your application-level
providers here — they run after the framework baseline and before the console
provider that collects every provider's commands.

Example::

    from app.providers.app_service_provider import AppServiceProvider

    providers = [AppServiceProvider]
"""

from __future__ import annotations

from arvel.providers import ServiceProvider

providers: list[type[ServiceProvider]] = []

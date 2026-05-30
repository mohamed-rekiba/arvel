"""Base class for Arvel service providers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from arvel.application import Application
    from arvel.console import Command
    from arvel.container import Container

_T = TypeVar("_T")


class ServiceProvider:
    """Bootstrap unit. Subclass to register bindings and run boot/shutdown logic."""

    app: Application
    container: Container

    def __init__(self, app: Application) -> None:
        self.app = app
        self.container = app.container

    def safe_config(self, cls: type[_T], *, default: _T) -> _T:
        """Resolve a config class from the container; return ``default`` on any failure.

        Use this when config is optional — the provider falls back to a safe
        default when the application hasn't registered the settings class.
        """
        try:
            return self.container.make(cls)
        except Exception:
            return default

    def register(self) -> None:
        """Sync. Container bindings only — no I/O, no other providers."""

    async def boot(self) -> None:
        """Async. May do I/O. Runs after every provider's register()."""

    async def shutdown(self) -> None:
        """Async. Tear down resources. Runs in reverse registration order."""

    def commands(self) -> list[type[Command] | Command]:
        """Console commands shipped by this provider (WI-020 FR-020-05).

        Each item may be either a ``Command`` subclass (instantiated with
        no args by ``ConsoleServiceProvider.boot()``) or a pre-built
        ``Command`` instance (used when the provider needs to inject
        dependencies that come from the container).
        """
        return []

    def provides(self) -> list[type]:
        """Abstracts this provider promises to bind. Used by deferred-provider logic (future WI)."""
        return []

    def publishes(
        self,
        paths: Mapping[str | Path, str | Path],
        *,
        tag: str = "default",
        is_migrations: bool = False,
    ) -> None:
        """Register source-to-destination publishables under ``tag``.

        Mirrors Laravel's ``$this->publishes([...], 'tag')``. Consumers run
        ``arvel vendor:publish --tag=<tag>`` (or ``--provider=<class>``) to
        copy the registered files into their app.

        Parameters
        ----------
        paths:
            Mapping of source file path → destination path. Both may be
            ``str`` or ``Path``. Relative destinations resolve against
            ``Application.base_path``.
        tag:
            Group label used by ``vendor:publish --tag=...``.
        is_migrations:
            When True, each destination is treated as a target *directory*
            and the basename is rewritten with a UTC timestamp at publish
            time so the file lands chronologically in
            ``database/migrations/``.
        """
        from arvel.application.errors import EnvironmentNotSetError
        from arvel.support.publishing import (
            PublishRegistry,
            normalize_publish_paths,
        )

        try:
            base_path = self.app.base_path()
        except EnvironmentNotSetError:
            # Bare Application (test scaffolding) — publishes() is metadata
            # for ``vendor:publish``, which only runs against a fully-built
            # app. Skip silently when there's nothing to publish into.
            return

        registry: PublishRegistry = self.container.make(PublishRegistry)
        registry.add(
            normalize_publish_paths(
                paths,
                base_path=base_path,
                tag=tag,
                provider=f"{type(self).__module__}.{type(self).__name__}",
                is_migrations=is_migrations,
            ),
        )

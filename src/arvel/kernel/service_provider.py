"""The ServiceProvider base + integration verbs.

The surface ecosystem packages and the app use to register into the framework:
``register()`` (sync, bindings only), ``boot()`` (sync or async), ``provides()``
(declare contracts for deferred loading), plus the integration verbs
(``merge_config_from``/``load_routes_from``/``commands``/``publishes``/…) that
record into the application's registries for later phases to consume.

Grounded in knowledge/port/03-application-providers-bootstrap.md + 19-ecosystem.
"""

from __future__ import annotations

import copy
import importlib.util
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from arvel.kernel.application import Application


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge ``override`` into ``base`` recursively (override wins)."""
    for key, value in override.items():
        existing = base.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            _deep_merge(cast("dict[str, Any]", existing), cast("Mapping[str, Any]", value))
        else:
            base[key] = value
    return base


def _load_config_file(path: str) -> Mapping[str, Any]:
    # executed as Python — load only from a trusted project tree, never an untrusted path
    if not str(path).endswith(".py"):
        raise ValueError(f"config file must be a .py module, got: {path!r}")
    spec = importlib.util.spec_from_file_location("_arvel_published_config", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = getattr(module, "config", None)
    if isinstance(config, Mapping):
        return cast("Mapping[str, Any]", config)
    return {k: getattr(module, k) for k in dir(module) if k.isupper()}


def _merge_defaults(repo: Any, key: str, defaults: Mapping[str, Any]) -> None:
    """Merge ``defaults`` under ``key`` so **existing values win** (fill gaps only).

    A deliberate scalar override is left untouched; nested dicts merge recursively; the defaults are
    deep-copied so a caller's source constant is never aliased into — or mutated through — the repo.
    """
    existing = repo.get(key)
    if repo.has(key) and not isinstance(existing, dict):
        return
    merged = copy.deepcopy(dict(defaults))
    if isinstance(existing, dict):
        _deep_merge(merged, cast("Mapping[str, Any]", existing))
    repo.set(key, merged)


def load_config_directory(app: Application, directory: str | None = None) -> None:
    """Auto-load ``{base_path}/config/*.py`` into the config repository.

    Each file contributes its ``config`` mapping (or its UPPERCASE module vars) under the file's
    **stem** — ``config/app.py`` → the ``app`` namespace. **Existing values win**, so anything set via
    ``with_config(...)`` overrides a file, and provider ``merge_config_from`` (run later) only fills
    remaining gaps. Files beginning with ``_`` are skipped; a missing directory is a no-op.

    Files are executed as Python (see ``_load_config_file``) — load only from a trusted project tree.
    """
    from pathlib import Path

    base = Path(directory) if directory is not None else Path(app.base_path) / "config"
    if not base.is_dir():
        return
    repo = app.make("config")
    for file in sorted(base.glob("*.py")):
        if file.name.startswith("_"):
            continue
        _merge_defaults(repo, file.stem, _load_config_file(str(file)))


class ServiceProvider:
    """Base class for framework, app, and ecosystem providers."""

    def __init__(self, app: Application) -> None:
        self.app = app

    def register(self) -> None:
        """Bind services into the container. Sync; no resolving, no I/O."""

    def boot(self) -> None | Awaitable[None]:
        """Boot-time wiring. May be overridden as ``async def`` — the application awaits the result
        when it returns an awaitable (so the return type permits both sync and async overrides)."""

    def provides(self) -> list[type[Any] | str]:
        """Contracts this provider supplies (container ``Abstract`` keys) — non-empty marks
        it *deferred*."""
        return []

    # --- integration verbs -------------------------------------------------
    def merge_config_from(self, source: str | Mapping[str, Any], key: str) -> None:
        """Merge package config defaults under ``key`` (existing app values win)."""
        defaults: Mapping[str, Any] = (
            source if isinstance(source, Mapping) else _load_config_file(source)
        )
        _merge_defaults(self.app.make("config"), key, defaults)

    def load_routes_from(self, path: str) -> None:
        self.app.route_files.append(path)

    def load_migrations_from(self, path: str) -> None:
        self.app.migration_paths.append(path)

    def load_views_from(self, path: str, namespace: str) -> None:
        self.app.view_namespaces[namespace] = path

    def load_translations_from(self, path: str, namespace: str) -> None:
        self.app.translation_namespaces[namespace] = path

    def commands(self, *cmds: Any) -> None:
        self.app.command_classes.extend(cmds)

    def publishes(self, mapping: Mapping[str, str], *, tag: str | None = None) -> None:
        self.app.published.setdefault(tag or "default", {}).update(mapping)

    def publishes_migrations(self, paths: Mapping[str, str], *, tag: str = "migrations") -> None:
        self.app.published.setdefault(tag, {}).update(paths)

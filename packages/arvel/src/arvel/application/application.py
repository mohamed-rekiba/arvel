"""Application kernel.

Public surface: ``Application``, ``ApplicationBuilder``. Builder is fluent; calling
``.create()`` produces a booted-ready ``Application`` (you still need to ``await app.boot()``).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from arvel.application.errors import (
    BootError,
    EnvironmentNotSetError,
    ServiceConnectError,
    ShutdownError,
)
from arvel.config.registry import register
from arvel.container import Container

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import Lifespan

    from arvel.config.settings import ArvelSettings
    from arvel.providers import ServiceProvider
    from arvel.routing import MiddlewareRef
    from arvel.services import BaseService


def _baseline_head_providers() -> list[type[ServiceProvider]]:
    """Framework providers that run BEFORE any user-listed providers.

    Order is dependency-driven:

    - ``ConfigServiceProvider``    — binds ``Config`` and every registered
      ``ArvelSettings`` subclass; everything else may rely on config lookups.
    - ``LogServiceProvider``       — binds the ``Log`` facade so later
      ``register()`` and ``boot()`` paths can emit structured logs.
    - ``LangServiceProvider``      — binds the translator so error messages
      from later providers can be localised.
    - ``ContextServiceProvider``   — reserves the request-context layer's slot
      so ``ContextMiddleware`` is mounted ahead of the database/HTTP stack.
    - ``ObservabilityServiceProvider`` — boots the OTel SDK, bridges uvicorn
      logging, and exports traces/logs when an OTLP endpoint is configured.
    - ``DatabaseServiceProvider``  — binds ``AsyncEngine`` /
      ``async_sessionmaker`` / ``AsyncSession`` so commands like
      ``arvel migrate`` and ORM-using code can resolve a real engine.
    - ``HttpServiceProvider``      — binds ``Router``, exception handler,
      rate-limit store, maintenance manager.
    - ``SchedulerServiceProvider`` — binds ``Schedule`` + ``SchedulerKernel``;
      its boot() auto-discovers ``app/console/kernel.py``.

    Imported lazily to avoid pulling SQLAlchemy / FastAPI into ``arvel`` core
    at module import time when the framework is used purely for, say, the
    ``new`` command outside a project.
    """
    from arvel.context.provider import ContextServiceProvider
    from arvel.observability import ObservabilityServiceProvider
    from arvel.providers import (
        ConfigServiceProvider,
        DatabaseServiceProvider,
        HttpServiceProvider,
        LangServiceProvider,
        LogServiceProvider,
        SchedulerServiceProvider,
    )

    return [
        ConfigServiceProvider,
        LogServiceProvider,
        LangServiceProvider,
        ContextServiceProvider,
        ObservabilityServiceProvider,
        DatabaseServiceProvider,
        HttpServiceProvider,
        SchedulerServiceProvider,
    ]


def _baseline_tail_providers() -> list[type[ServiceProvider]]:
    """Framework providers that always run AFTER every other provider.

    ``ConsoleServiceProvider.boot()`` walks every registered provider and
    invokes its ``commands()`` to merge them into the console ``Application``.
    Pinning it last guarantees user-defined providers (which may expose
    ``commands()``) are visible to it.
    """
    from arvel.console.providers.console_service_provider import ConsoleServiceProvider

    return [ConsoleServiceProvider]


class Application:
    """The framework kernel — owns the root container + provider lifecycle."""

    container: Container

    def __init__(self) -> None:
        from arvel.support.publishing import PublishRegistry

        self.container = Container()
        self.container.instance(Application, self)
        self.container.instance(PublishRegistry, PublishRegistry())
        self._environment: str | None = None
        self._base_path: Path | None = None
        self._provider_classes: list[type[ServiceProvider]] = []
        self._provider_instances: list[ServiceProvider] = []
        self._services: list[BaseService] = []
        self._booted: bool = False

    def register_service(self, service: BaseService) -> None:
        """Register a ``BaseService`` into the managed lifecycle.

        ``connect()`` runs at boot (registration order); ``disconnect()`` at
        shutdown (reverse). Registering after boot connects immediately is *not*
        supported — register before ``boot()``.
        """
        self._services.append(service)

    def services(self) -> list[BaseService]:
        return list(self._services)

    def register(self) -> None:
        """Bootstrap the framework's baseline providers without a project base_path.

        Convenience for test setups that need a minimal Application with container
        bindings but don't need a full project directory. Production code should
        use Application.configure(base_path).create() instead.
        """
        self._init_from_builder(
            base_path=Path(),
            environment="testing",
            providers=[],
        )
        # Register Gate as a singleton so it accumulates abilities across resolutions.
        from arvel.auth.gate import Gate  # gate imported late to avoid circular import

        if not self.container.bound(Gate):
            self.container.singleton(Gate, Gate)

    def make(self, key: str, **overrides: object) -> Any:
        """Resolve a named binding from the container."""
        return self.container.make(key, **overrides)  # type: ignore[arg-type]

    def middleware_group(self, name: str, middleware: Sequence[MiddlewareRef]) -> None:
        from arvel.routing import Router

        Router.singleton().middleware_group(name, middleware)

    def iter_providers(self) -> Iterator[ServiceProvider]:
        """Yield each registered ServiceProvider instance, in registration order.

        Used by ConsoleServiceProvider.boot to collect commands from
        every provider without reaching into ``_provider_instances`` directly.
        """
        yield from self._provider_instances

    @classmethod
    def configure(cls, base_path: Path | str) -> ApplicationBuilder:
        return ApplicationBuilder(Path(base_path))

    def environment(self) -> str:
        if self._environment is None:
            raise EnvironmentNotSetError(
                "Application.with_environment() was not called before .create().",
            )
        return self._environment

    def base_path(self) -> Path:
        if self._base_path is None:
            raise EnvironmentNotSetError("Application.base_path is not set.")
        return self._base_path

    def use_base_path(self, path: Path) -> None:
        self._base_path = path

    async def boot(self) -> None:
        if self._booted:
            return

        # Provider instances + sync register() ran at create-time; this is
        # just the async boot pass.
        for inst in self._provider_instances:
            try:
                await inst.boot()
            except Exception as exc:
                raise BootError(type(inst), exc) from exc

        from arvel.logging.facade import Log
        from arvel.routing import Router

        for service in self._services:
            try:
                await service.connect()
            except Exception as exc:
                raise ServiceConnectError(service.name, exc) from exc
            Log.info("service.connected", service=service.name)

        self._booted = True
        self._log_registered_routes()
        Log.info(
            "app.boot.complete",
            environment=self._environment or "",
            services=len(self._services),
            routes=len(Router.singleton().routes()),
        )

    def _log_registered_routes(self) -> None:
        """Emit one DEBUG log per registered route once every provider has booted.

        Function names / module paths only ever show up at DEBUG, so external
        aggregators don't see internal structure at INFO and above.
        """
        from arvel.logging.facade import Log
        from arvel.routing import Router

        for spec in Router.singleton().routes():
            Log.debug(
                "route.registered",
                method=spec.method,
                path=spec.path,
                name=spec.name or "",
            )

    def _init_from_builder(
        self,
        *,
        base_path: Path,
        environment: str,
        providers: list[type[ServiceProvider]],
    ) -> None:
        self._base_path = base_path
        self._environment = environment
        self._provider_classes = self._resolve_provider_chain(providers)

        # Instantiate providers and run the sync register() pass eagerly. This
        # makes all container bindings available the moment .create() returns,
        # so callers can compose ASGI apps, run sync diagnostics, or hand the
        # container to other layers before awaiting boot(). The async boot()
        # pass still runs lazily via Application.boot() (typically driven by
        # the ASGI lifespan startup wired in into_asgi()).
        instances: list[ServiceProvider] = [cls(self) for cls in self._provider_classes]
        self._provider_instances = instances
        for inst in instances:
            try:
                inst.register()
            except Exception as exc:
                raise BootError(type(inst), exc) from exc

    @classmethod
    def _resolve_provider_chain(
        cls, user_providers: list[type[ServiceProvider]]
    ) -> list[type[ServiceProvider]]:
        """Compose the canonical provider chain.

        Order:
          1. Framework HEAD baseline (Config → Log → Lang → Database → Http → Scheduler)
          2. User providers (any baseline duplicates are skipped)
          3. Framework TAIL (ConsoleServiceProvider) — always last so its
             ``boot()`` can collect ``commands()`` from every other provider

        Listing a HEAD provider in ``user_providers`` is a no-op (already in
        HEAD). Listing the TAIL provider in ``user_providers`` is overridden —
        it always runs last regardless of where the user placed it.
        """
        head = _baseline_head_providers()
        tail = _baseline_tail_providers()
        tail_set = set(tail)

        seen: set[type[ServiceProvider]] = set()
        chain: list[type[ServiceProvider]] = []

        def add(provider_cls: type[ServiceProvider]) -> None:
            if provider_cls in seen:
                return
            seen.add(provider_cls)
            chain.append(provider_cls)

        for provider_cls in head:
            add(provider_cls)
        for provider_cls in user_providers:
            if provider_cls in tail_set:
                # Force tail providers to the end even if user listed them mid-chain.
                continue
            add(provider_cls)
        for provider_cls in tail:
            add(provider_cls)

        return chain

    async def shutdown(self) -> None:
        if not self._booted:
            return
        # Disconnect services first (reverse registration). A failing disconnect
        # is logged, not raised, so the remaining services still tear down.
        for service in reversed(self._services):
            try:
                await service.disconnect()
            except Exception as exc:  # noqa: BLE001 — one bad disconnect must not strand the rest
                from arvel.logging.facade import Log

                Log.error("service.disconnect_failed", exc=exc, service=service.name)
        for inst in reversed(self._provider_instances):
            try:
                await inst.shutdown()
            except Exception as exc:
                raise ShutdownError(type(inst), exc) from exc
        self._booted = False

    def into_asgi(
        self,
        *,
        lifespan: Lifespan[FastAPI] | None = None,
        **fastapi_kwargs: Any,
    ) -> FastAPI:
        """Produce a fully wired ASGI app. The framework owns the lifecycle.

        Boot and shutdown are driven by the ASGI lifespan protocol, not by
        this factory call. That keeps the method loop-agnostic — it works the
        same whether called from a plain sync entrypoint or from inside a
        uvicorn ``--factory`` callback (which uvicorn invokes from within its
        own running event loop).

        Behaviour:

        - Always returns a configured ``FastAPI`` instance (re-exported as
          ``arvel.ASGIApp``). Routes are mounted, the exception handler is
          wired, and the container is stashed on ``app.state.arvel_container``.
        - When ``lifespan`` is omitted, wires a default lifespan that calls
          ``await self.boot()`` on startup (skipped if already booted) and
          ``await self.shutdown()`` on graceful exit.
        - When ``lifespan`` is provided, uses it verbatim — the caller takes
          ownership of boot and shutdown.
        - ``**fastapi_kwargs`` are forwarded verbatim to the ``FastAPI``
          constructor (e.g. ``docs_url``, ``redoc_url``, ``openapi_url``,
          ``title``, ``version``).

        The returned app expects to be driven by a lifespan-aware ASGI host
        (uvicorn, hypercorn, Starlette ``TestClient`` used as a context
        manager). Routing still works without a lifespan, but providers will
        not have booted.
        """
        from fastapi import FastAPI

        from arvel.http.exceptions import HttpExceptionHandler
        from arvel.http.middleware.scope import ArvelScopeMiddleware
        from arvel.routing import Router

        effective_lifespan = lifespan if lifespan is not None else self._default_lifespan()

        fa = FastAPI(lifespan=effective_lifespan, **fastapi_kwargs)
        fa.state.arvel_container = self.container
        handler = self.container.make(HttpExceptionHandler)
        handler.register(fa)
        router = self.container.make(Router)
        router.register_with_app(fa)
        self._add_health_route(fa)
        self._maybe_mount_public_storage(fa)
        self._maybe_add_maintenance_middleware(fa)
        # add_middleware prepends, so the LAST call is the OUTERMOST layer.
        # Desired outer→inner: Observability → Context → DeferredTask → ArvelScope.
        fa.add_middleware(ArvelScopeMiddleware, container=self.container)
        self._maybe_add_observability_middleware(fa)
        return fa

    def _add_health_route(self, fa: FastAPI) -> None:
        from arvel.container.errors import BindingResolutionError
        from arvel.health import add_health_route
        from arvel.observability.config import ObservabilityConfig

        try:
            config = self.container.make(ObservabilityConfig)
        except BindingResolutionError:
            config = ObservabilityConfig()
        add_health_route(fa, container=self.container, allowed_cidrs=config.health_allowed_cidrs)

    def _maybe_add_observability_middleware(self, fa: FastAPI) -> None:
        """Mount the context + observability middleware unless explicitly disabled."""
        from arvel.container.errors import BindingResolutionError
        from arvel.context import ContextMiddleware, DeferredTaskMiddleware
        from arvel.observability import ObservabilityMiddleware
        from arvel.observability.config import ObservabilityConfig

        try:
            config = self.container.make(ObservabilityConfig)
        except BindingResolutionError:
            config = ObservabilityConfig()
        if not config.request_middleware_enabled:
            return

        fa.add_middleware(DeferredTaskMiddleware)
        fa.add_middleware(ContextMiddleware)
        fa.add_middleware(
            ObservabilityMiddleware,
            service=config.service_name,
            log_requests=not config.log_uvicorn_access,
        )

    def _maybe_mount_public_storage(self, fa: FastAPI) -> None:
        """Serve the `storage:link` symlink (public/storage) at /storage.

        Mounted only when the link exists at boot — run `storage:link` then
        (re)start the server. Until then the path 404s through the framework.
        Scoped to public/storage, never the public/ parent, so the ASGI
        entrypoint (public/asgi.py) can't be served as source. See ADR-137.
        """
        from starlette.staticfiles import StaticFiles

        storage_dir = self.base_path() / "public" / "storage"
        # .exists() follows the symlink, so a dangling link is treated as absent.
        if not storage_dir.exists():
            return
        fa.mount(
            "/storage",
            StaticFiles(directory=storage_dir),
            name="storage.public",
        )

    def _maybe_add_maintenance_middleware(self, fa: FastAPI) -> None:
        """Attach the maintenance middleware if a manager is bound."""
        from arvel.container.errors import BindingResolutionError
        from arvel.maintenance import (
            MaintenanceModeManager,
            MaintenanceModeMiddleware,
        )

        try:
            manager = self.container.make(MaintenanceModeManager)
        except BindingResolutionError:
            return
        fa.add_middleware(MaintenanceModeMiddleware, manager=manager)

    def _default_lifespan(self) -> Lifespan[FastAPI]:
        @asynccontextmanager
        async def lifespan(_asgi_app: FastAPI) -> AsyncGenerator[None]:
            if not self._booted:
                await self.boot()
            try:
                yield
            finally:
                await self.shutdown()

        return lifespan


def serve(app: Application, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the app under uvicorn.

    Auto-boots the application if it has not been booted yet (via
    ``Application.into_asgi()``), so this is callable from a plain sync
    entrypoint.
    """
    import os

    import uvicorn

    raw = os.environ.get("GRACEFUL_SHUTDOWN_TIMEOUT", "").strip()
    timeout = int(raw) if raw.isdigit() else None
    uvicorn.run(app.into_asgi(), host=host, port=port, timeout_graceful_shutdown=timeout)


class ApplicationBuilder:
    """Fluent builder for ``Application``."""

    def __init__(self, base_path: Path) -> None:
        self._base_path: Path = base_path
        self._providers: list[type[ServiceProvider]] = []
        self._providers_path: Path | None = None
        self._environment: str | None = None
        self._config_classes: list[type[ArvelSettings]] = []
        self._config_dir: Path | None = None
        self._routing_paths: dict[str, Path] = {}

    def with_providers(self, providers: list[type[ServiceProvider]] | Path | str) -> Self:
        if isinstance(providers, list):
            self._providers.extend(providers)
            return self
        # Path or str: defer loading until .create() — needed for the Laravel-shaped
        # skeleton where bootstrap/providers.py declares `providers = [...]` at
        # module scope.
        self._providers_path = Path(providers) if isinstance(providers, str) else providers
        return self

    def with_environment(self, name: str) -> Self:
        self._environment = name
        return self

    def with_config_files(self, config_classes: list[type[ArvelSettings]]) -> Self:
        for cls in config_classes:
            register(cls)
            self._config_classes.append(cls)
        return self

    def with_routing(
        self,
        *,
        web: Path | str | None = None,
        api: Path | str | None = None,
        console: Path | str | None = None,
    ) -> Self:
        """Register routing file paths to be loaded at register time.

               ``web`` and ``api`` are loaded by ``HttpServiceProvider.register``.
               ``console`` is stored on the application but not loaded until the
               Console provider ships.

               At least one of the three must be non-None. Subsequent calls
        accumulate (last-write-wins per key).
        """
        if web is None and api is None and console is None:
            msg = "with_routing() requires at least one of web=, api=, console="
            raise ValueError(msg)
        if web is not None:
            self._routing_paths["web"] = Path(web) if isinstance(web, str) else web
        if api is not None:
            self._routing_paths["api"] = Path(api) if isinstance(api, str) else api
        if console is not None:
            self._routing_paths["console"] = Path(console) if isinstance(console, str) else console
        return self

    def with_config_dir(self, path: Path | str) -> Self:
        """Discover and load every ``.py`` config file in ``path`` at register() time.

        See ``arvel.application._loader.discover_config_files`` for the
        discovery rules and ``arvel.config.lookup`` for the runtime accessor.
        Files are loaded under namespaced module names so a user's
        ``config/logging.py`` never shadows stdlib ``logging``.
        """
        self._config_dir = Path(path) if isinstance(path, str) else path
        return self

    def create(self) -> Application:
        # Load .env into os.environ before config modules execute so that
        # env() calls inside config/*.py see the same values pydantic-settings
        # would read from .env. os.environ values always win (override=False).
        self._load_dotenv()
        if self._config_dir is not None:
            self._load_config_dir()
        if self._providers_path is not None:
            self._load_providers_from_path()

        # Routing files are loaded before providers run their register() pass so
        # that Router.reset_singleton() (called inside _load_routing_files) cannot
        # wipe routes that providers register synchronously in register() — e.g.
        # AuthServiceProvider mounts /api/auth/* during register(), not boot().
        if self._routing_paths:
            self._load_routing_files()

        app = Application()
        app._init_from_builder(  # pyright: ignore[reportPrivateUsage]
            base_path=self._base_path,
            environment=self._resolve_environment(),
            providers=list(self._providers),
        )
        return app

    def _resolve_environment(self) -> str:
        if self._environment is not None:
            return self._environment
        from arvel.config._lookup_registry import config as _cfg
        from arvel.support.env import env as _env

        raw = _cfg("app.env")
        if isinstance(raw, str) and raw:
            return raw
        return _env("APP_ENV", "production").lower()

    def _load_dotenv(self) -> None:
        """Load ``.env`` from base_path into os.environ (does not override existing vars).

        This ensures env() calls inside config/*.py see the same values that
        pydantic-settings would read later when instantiating ArvelSettings subclasses.
        """
        from dotenv import load_dotenv

        dotenv_path = self._base_path / ".env"
        if dotenv_path.exists():
            load_dotenv(dotenv_path, override=False)

    def _load_config_dir(self) -> None:
        from arvel.application._loader import (
            NAMESPACE_PREFIX,
            discover_config_files,
            load_module_from_path,
        )
        from arvel.config._lookup_registry import load_from_cache, register, reset

        # Caller guard: this private method runs only after with_config_dir(...)
        # set _config_dir. Raise (rather than assert) so the invariant holds
        # even under `python -O`, and bandit/ruff stay quiet at the source.
        if self._config_dir is None:
            msg = "_load_config_dir called before with_config_dir(...)"
            raise RuntimeError(msg)
        # Reset the registry so two apps in the same process don't see each other's modules.
        reset()
        # Fast path: use the compiled cache when present.
        cache_path = self._base_path / "bootstrap" / "cache" / "config.json"
        if cache_path.exists() and load_from_cache(cache_path):
            return
        for file in discover_config_files(self._config_dir):
            module_name = f"{NAMESPACE_PREFIX}.config.{file.stem}"
            module = load_module_from_path(file, module_name)
            register(file.stem, module)

    def _load_routing_files(self) -> None:
        """Import each registered routing file so its decorators populate ``Router``.

               Only ``web`` and ``api`` are loaded initially. ``console`` is stored
               for a future Console provider. Files load through the
        ``_loader`` so the ``sys.path`` invariant holds and config-style
        module shadowing is avoided.
        """
        from arvel.application._loader import NAMESPACE_PREFIX, load_module_from_path
        from arvel.routing import Router

        # Routes accumulate on every exec_module call because the loader
        # bypasses sys.modules caching. Reset before each load so multiple
        # create() calls in the same process don't duplicate routes.
        Router.reset_singleton()

        for key in ("web", "api"):
            path = self._routing_paths.get(key)
            if path is None:
                continue
            load_module_from_path(path, f"{NAMESPACE_PREFIX}.routes.{key}")

    def _load_providers_from_path(self) -> None:
        from arvel.application._loader import NAMESPACE_PREFIX, load_module_from_path
        from arvel.providers import ServiceProvider as _ServiceProvider

        # Caller guard: this private method runs only after with_providers_path(...)
        # set _providers_path. Raise (not assert) so the invariant survives `-O`.
        if self._providers_path is None:
            msg = "_load_providers_from_path called before with_providers_path(...)"
            raise RuntimeError(msg)
        path = self._providers_path
        module = load_module_from_path(path, f"{NAMESPACE_PREFIX}.bootstrap.providers")
        if not hasattr(module, "providers"):
            msg = (
                f"providers module at {path} does not declare a top-level "
                f"`providers` attribute. Expected: providers: list[type[ServiceProvider]] = [...]"
            )
            raise RuntimeError(msg)
        raw_value: object = module.providers
        if not isinstance(raw_value, list):
            msg = (
                f"providers attribute in {path} is {raw_value!r}; "
                f"expected list[type[ServiceProvider]]."
            )
            raise TypeError(msg)
        # Narrow item-by-item so the resulting list has a concrete element type
        # that .extend() can consume without unknown-type leakage.
        validated: list[type[_ServiceProvider]] = []
        # isinstance(raw_value, list) narrows to list[Unknown] under pyright; the
        # explicit annotation widens for the loop body, hence the local ignore.
        raw_items: list[Any] = raw_value  # pyright: ignore[reportUnknownVariableType]
        for item in raw_items:
            if not (isinstance(item, type) and issubclass(item, _ServiceProvider)):
                msg = (
                    f"providers attribute in {path} is {raw_value!r}; "
                    f"expected list[type[ServiceProvider]]."
                )
                raise TypeError(msg)
            validated.append(item)
        self._providers.extend(validated)

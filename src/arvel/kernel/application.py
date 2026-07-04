"""The Application — a container that registers providers and boots them.

``Application`` extends :class:`~arvel.kernel.container.Container` with the
register→boot lifecycle, a lifecycle **hook bus** (``booting``/``booted``/
``terminating``), ``terminating()`` shutdown callbacks, and dotted ``config()``.
``ApplicationBuilder`` is the fluent front door (``Application.configure(...)``).

Entry-point **provider discovery** (``arvel.kernel.discovery``), the ``ServiceProvider``
integration verbs, and the ASGI ``lifespan`` (``arvel.kernel.bootstrap``) are all wired in.
Grounded in knowledge/port/03-application-providers-bootstrap.md.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, overload

from arvel.kernel.config import Repository
from arvel.kernel.container import Container
from arvel.kernel.globals import set_application
from arvel.kernel.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from arvel.contracts import ServiceProvider

#: A provider given to the builder: an instance, or a class taking ``(app)``.
#: Typed ``Any`` because the concrete ``ServiceProvider`` base (constructible with
#: ``app``) lands in T1.4; here it may be a duck-typed instance or class.
ProviderInput = Any


class Application(Container):
    """The arvel application container."""

    @classmethod
    def version(cls) -> str:
        """The installed arvel version (single-sourced from package metadata, which derives from
        ``arvel.__version__`` via the dynamic build — V1). Lazy so it adds no import-time cost."""
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as _dist_version

        try:
            return _dist_version("arvel")
        except PackageNotFoundError:  # pragma: no cover - not installed as a dist (rare)
            return "0.0.0"

    def __init__(self, base_path: str = ".") -> None:
        super().__init__()
        self.base_path = str(base_path)
        self._providers: list[ServiceProvider] = []
        self._booted = False
        self.bootstrapped = False  # sync bootstrap_app() has run (idempotency guard)
        self._terminating: list[Callable[[], Any]] = []
        self._hooks: dict[str, list[Callable[[Application], Any]]] = {}
        self.instance("app", self)
        self.instance(Container, self)
        self.instance(Application, self)
        if "config" not in self._instances:
            self.instance("config", Repository())
        # registries populated by ServiceProvider integration verbs (T1.4)
        self.route_files: list[str] = []
        self.migration_paths: list[str] = []
        self.view_namespaces: dict[str, str] = {}
        self.translation_namespaces: dict[str, str] = {}
        self.command_classes: list[Any] = []
        self.console_commands: dict[str, Any] = {}  # name -> ClosureCommand (routes/console.py)
        self.published: dict[str, dict[str, str]] = {}
        self.app_provider_classes: list[type] = []
        self.registered_provider_types: set[type] = set()
        self._deferred: dict[Any, Any] = {}
        # builder-supplied config (ApplicationBuilder.with_routing/middleware/exceptions)
        self.routing: dict[str, Any] = {}
        self.config_dir: str | None = None  # with_config_dir override (else {base_path}/config)
        self.public_dir: str | None = (
            None  # with_public_dir — auto-registers Route.public() at boot
        )
        self.public_path: str = "/"  # with_public_dir(..., path=...) — mount point, e.g. a sub-path
        self.public_spa_fallback: bool = True  # with_public_dir(..., spa_fallback=...)
        self.lang_dir: str | None = None  # with_lang_dir override (else {base_path}/lang)
        self._builder_middlewares: list[Any] = []
        self._builder_exceptions: Callable[[Any], Any] | None = None

    @property
    def booted_provider_count(self) -> int:
        """Count of providers actually booted (the eager set). Deferred providers are registered but
        not booted until first resolved, so this is < ``len(registered_provider_types)`` whenever a
        provider is deferred — letting the boot report distinguish booted from merely discovered."""
        return len({type(provider) for provider in self._providers})

    @classmethod
    def configure(cls, base_path: str = ".") -> ApplicationBuilder:
        return ApplicationBuilder(cls(base_path))

    # --- providers ---------------------------------------------------------
    def register(self, provider: ServiceProvider) -> ServiceProvider:
        provider.register()
        self._providers.append(provider)
        self.registered_provider_types.add(type(provider))
        if self._booted:  # registered after the boot loop → boot it now + re-finalize (B8/B3)
            self._boot_deferred(provider)
            self._register_translation_namespaces()
        return provider

    def register_deferred(self, provider: ServiceProvider) -> None:
        """Record a provider whose ``register()`` runs only when one of its
        ``provides()`` contracts is first resolved (keeps startup lean)."""
        self.registered_provider_types.add(type(provider))
        for abstract in provider.provides():
            self._deferred[self._alias_of(abstract)] = provider

    def resolvable(self, abstract: Any) -> bool:
        """Whether ``abstract`` can be resolved — it's ``bound()`` OR provided by a not-yet-loaded
        deferred provider (which registers on first ``make``). Distinct from ``bound()``, which (like
        Laravel) reports only *materialized* bindings — a deferred service isn't ``bound()`` until it
        first resolves."""
        return self.bound(abstract) or self._alias_of(abstract) in self._deferred

    def flush(self) -> None:
        """Clear the container, then re-seed the application's own self-bindings + drop deferred
        providers — so an ``Application`` stays usable after a flush (a bare ``Container.flush()``
        would wipe the ``app``/``Container``/``Application``/``config`` self-bindings and leave it
        unresolvable). Registries (route_files, etc.) are left intact — flush is container-scoped."""
        super().flush()
        self._deferred.clear()
        self.instance("app", self)
        self.instance(Container, self)
        self.instance(Application, self)
        self.instance("config", Repository())

    def _resolve(self, abstract: Any, params: dict[str, Any] | None = None) -> Any:
        key = self._alias_of(abstract)
        provider = self._deferred.get(key)
        if provider is not None and key not in self._bindings and key not in self._instances:
            self._deferred = {k: v for k, v in self._deferred.items() if v is not provider}
            self.register(provider)  # register() boots it too when the app is already booted (B8)
        return super()._resolve(abstract, params)

    def _boot_deferred(self, provider: ServiceProvider) -> None:
        """Boot a provider registered/triggered *after* the app booted — otherwise its ``boot()``
        never runs (the boot loop already finished). A sync ``boot()`` runs inline; an async
        ``boot()`` can't be awaited from this sync path, so deferred providers should keep ``boot()``
        synchronous (their async work belongs in a non-deferred provider)."""
        result = self.call((provider, "boot"))
        if inspect.isawaitable(result):
            cast("Any", result).close()  # close the unawaited coroutine
            from arvel.kernel.logging import LogManager

            # B2: a post-boot async deferred boot() is dropped — warn loudly instead of swallowing it
            # silently, so the no-op is diagnosable (keep deferred boot() synchronous).
            LogManager().channel("kernel").warning(
                "async_deferred_boot_skipped",
                provider=type(provider).__name__,
                hint="make a deferred provider's boot() synchronous (async work belongs in a "
                "non-deferred provider)",
            )

    async def boot(self) -> None:
        if self._booted:
            return
        await self._fire("booting")
        for provider in self._providers:
            await self._boot_provider(provider)
        self._register_translation_namespaces()
        self._apply_builder_overrides()
        self._booted = True
        await self._fire("booted")

    def use_builder_config(
        self,
        routing: dict[str, Any],
        middlewares: list[Any],
        exceptions: Callable[[Any], Any] | None,
    ) -> None:
        """Adopt the fluent ApplicationBuilder config (C2). Route files feed the registry boot
        reads; the global middleware list + exception configurator are applied at boot against
        their bound targets."""
        self.routing.update(routing)
        # `console` is a CLI-command file (loaded by the console kernel), not an HTTP route file —
        # keep it out of the HTTP route registry. web/api/other named groups feed the router.
        self.route_files.extend(path for name, path in routing.items() if name != "console")
        self._builder_middlewares = middlewares
        self._builder_exceptions = exceptions

    def _apply_builder_overrides(self) -> None:
        """Apply builder-supplied config against the now-bound targets (C2): ``with_exceptions``
        customizes the bound exception handler. ``with_middlewares`` is NOT applied here — the served
        ``HttpKernel`` is built on demand in ``_build_served_asgi`` (it is not a container singleton;
        ``"http"`` is the HTTP *client*), which consumes ``builder_middlewares`` there."""
        if self._builder_exceptions is not None and self.bound("exceptions"):
            self._builder_exceptions(self.make("exceptions"))

    @property
    def builder_middlewares(self) -> Sequence[Any]:
        """Global middleware registered via the fluent ``with_middlewares([...])`` — consumed by the
        served kernel builder (``_build_served_asgi``) so they run on every request."""
        return self._builder_middlewares

    def _register_translation_namespaces(self) -> None:
        """Apply provider-registered translation namespaces (``load_translations_from``) to the
        bound translator, so packages' ``pkg::group.key`` translations resolve at runtime."""
        if not self.translation_namespaces or not self.bound("translator"):
            return
        register = getattr(self.make("translator"), "add_namespace", None)
        if callable(register):
            for namespace, path in self.translation_namespaces.items():
                register(namespace, path)

    async def _boot_provider(self, provider: ServiceProvider) -> None:
        result = self.call((provider, "boot"))
        if inspect.isawaitable(result):
            await result

    @property
    def booted(self) -> bool:
        return self._booted

    # --- lifecycle hook bus ------------------------------------------------
    def on(self, event: str, callback: Callable[[Application], Any]) -> None:
        """Subscribe to a lifecycle event (``booting``/``booted``/``terminating``)."""
        self._hooks.setdefault(event, []).append(callback)

    async def _fire(self, event: str) -> None:
        for callback in self._hooks.get(event, []):
            result = callback(self)
            if inspect.isawaitable(result):
                await result

    # --- shutdown ----------------------------------------------------------
    def terminating(self, callback: Callable[[], Any]) -> None:
        self._terminating.append(callback)

    async def terminate(self) -> None:
        await self._fire("terminating")
        # LIFO (T1): dispose in reverse order of registration, like nested context managers, so a
        # dependency isn't torn down before the resource that depends on it.
        for callback in reversed(self._terminating):
            result = callback()
            if inspect.isawaitable(result):
                await result

    # --- serve -------------------------------------------------------------
    def as_asgi(self) -> Any:
        """Compile the registered routes into the served ASGI app (a litestar.Litestar).

        Runs the **synchronous** bootstrap first (``bootstrap_app``: env, config, provider
        registration → the router and other bindings exist), then resolves the served-ASGI
        builder the routing provider bound under ``http.asgi_builder``. The kernel must not
        import ``arvel.http`` (kernel→capability is forbidden, DR-0026); the build logic lives
        in ``arvel.routing`` (a legal downward edge) and is reached through the container — so
        ``import arvel`` and the T0 CLI stay light (G2) without a kernel→http edge."""
        from arvel.kernel.bootstrap import bootstrap_app

        bootstrap_app(self)  # sync prep: env → config → providers register (binds router + builder)
        return self.make("http.asgi_builder")(self)

    # --- config convenience ------------------------------------------------
    @overload
    def config(self) -> Repository: ...
    @overload
    def config(self, key: str, default: Any = None) -> Any: ...
    def config(self, key: str | None = None, default: Any = None) -> Any:
        repo = self.make("config")
        return repo if key is None else repo.get(key, default)


def _load_bootstrap_module(path: Path) -> Any | None:
    """Execute a bootstrap Python file (``providers.py`` / ``middlewares.py``) and return its module,
    or ``None`` if it doesn't exist. Run as Python — the project tree is trusted, like config files."""
    import importlib.util

    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"_arvel_bootstrap_{path.stem}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplicationBuilder:
    """Fluent application configuration (``Application.configure(...).create()``)."""

    def __init__(self, app: Application) -> None:
        self._app = app
        self._providers: list[ProviderInput] = []
        self._config: dict[str, Any] = {}
        self._config_dir: str | None = None
        self._public_dir: str | None = None
        self._public_path: str = "/"
        self._public_spa_fallback: bool = True
        self._lang_dir: str | None = None
        self._routing: dict[str, Any] = {}
        self._middlewares: list[Any] = []
        self._exceptions: Callable[[Any], Any] | None = None

    def with_config(self, items: Mapping[str, Any]) -> ApplicationBuilder:
        self._config.update(items)
        return self

    def with_config_dir(self, directory: str | Path) -> ApplicationBuilder:
        """Load config from ``directory`` instead of the default ``{base_path}/config``."""
        self._config_dir = str(directory)
        return self

    def with_public_dir(
        self, directory: str | Path, *, path: str = "/", spa_fallback: bool = True
    ) -> ApplicationBuilder:
        """Serve ``directory`` as the app's public web root — Laravel's ``public/`` (see
        ``Router.public()`` for the full rationale). Registers automatically at boot
        (``RoutingServiceProvider``); no route-file code needed at all, matching how Laravel's
        own webserver-served ``public/`` needs zero lines in ``routes/web.php``. ``path`` mounts
        it under a sub-path (e.g. ``/app``) instead of the root; ``spa_fallback=False`` serves
        only real files (favicon/robots/storage/...) and 404s on an unmatched path instead of
        falling back to ``index.html`` — for an app with no client-side router. Both are the same
        params ``Router.public()`` itself takes."""
        self._public_dir = str(directory)
        self._public_path = path
        self._public_spa_fallback = spa_fallback
        return self

    def with_lang_dir(self, directory: str | Path) -> ApplicationBuilder:
        """Load translations from ``directory`` instead of the default ``{base_path}/lang``
        (e.g. ``resources/lang``, the pre-Laravel-9 convention) — ``LocalizationServiceProvider``
        loads the app's own translations from here, after the framework's bundled defaults."""
        self._lang_dir = str(directory)
        return self

    def with_providers(self, providers: str | Path | Sequence[ProviderInput]) -> ApplicationBuilder:
        """Register service providers — a list of provider classes/instances, OR a path to a Python
        file exposing a ``providers = [...]`` list (Laravel's ``bootstrap/providers.php`` shape)."""
        if isinstance(providers, str | Path):
            module = _load_bootstrap_module(Path(providers))
            resolved: Sequence[ProviderInput] = (
                getattr(module, "providers", []) if module is not None else []
            )
        else:
            resolved = providers
        self._providers.extend(resolved)
        return self

    def with_routing(self, **routes: Any) -> ApplicationBuilder:
        """Register route files by named group: ``web``/``api`` are HTTP route files (loaded into the
        router under the matching middleware group; ``api`` is also URL-prefixed ``/api``), and
        ``console`` is a CLI-command file (reserved for the console kernel — loader pending — and
        excluded from the HTTP router)."""
        self._routing.update({name: str(path) for name, path in routes.items()})
        return self

    def with_middlewares(self, middlewares: str | Path | Sequence[Any]) -> ApplicationBuilder:
        """Register global HTTP middleware — a list of middleware classes/instances/aliases, OR a
        path to a Python file exposing a ``middlewares = [...]`` list. They append to the HTTP
        kernel's global stack (run for every request) at boot."""
        if isinstance(middlewares, str | Path):
            module = _load_bootstrap_module(Path(middlewares))
            resolved: Sequence[Any] = (
                getattr(module, "middlewares", []) if module is not None else []
            )
        else:
            resolved = middlewares
        self._middlewares.extend(resolved)
        return self

    def with_exceptions(self, configure: Callable[[Any], Any]) -> ApplicationBuilder:
        self._exceptions = configure
        return self

    def create(self) -> Application:
        app = self._app
        if self._config:
            app.instance("config", Repository(self._config))
        if self._config_dir is not None:
            app.config_dir = self._config_dir
        if self._public_dir is not None:
            app.public_dir = self._public_dir
            app.public_path = self._public_path
            app.public_spa_fallback = self._public_spa_fallback
        if self._lang_dir is not None:
            app.lang_dir = self._lang_dir
        set_application(app)
        for provider in self._providers:
            instance = provider(app) if isinstance(provider, type) else provider
            app.register(instance)
            # provider is duck-typed Any (concrete base lands per-package); its class is a type.
            app.app_provider_classes.append(cast("type[Any]", type(instance)))
        # consume the fluent builder config (C2 — was previously dropped on the floor)
        app.use_builder_config(self._routing, self._middlewares, self._exceptions)
        return app


class AppSettings(Settings):
    """Typed, validated view over the core ``app`` config section (DR-0016).

    ``env`` stays ``str`` (env names are an open convention — ``local``/``staging``/``production`` but
    also custom). Note: the framework's *own* foundational reads of ``app.*`` (e.g. ``app.timezone`` in
    ``arvel.dates``, ``app.name`` in ``arvel.contracts``) stay on raw ``config()`` — those modules are
    below ``kernel.settings`` in the import layering and can't depend on it. This view is for app code.
    """

    __config_key__ = "app"
    name: str = "arvel"
    env: str = "local"
    debug: bool = False
    timezone: str = "UTC"

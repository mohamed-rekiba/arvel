"""Application kernel — bootstrap, provider lifecycle, ASGI factory.

This is the entry point for every Arvel application.  ``Application.configure``
returns an ASGI-compatible app that bootstraps lazily on the first ASGI event
— no async work at import time, no FastAPI leak to userland.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from arvel.foundation.config import AppSettings, ModuleSettings, get_module_settings, load_config
from arvel.foundation.container import (  # noqa: TC001
    Container,
    ContainerBuilder,
    Scope,
)
from arvel.foundation.exceptions import BootError, ConfigurationError, ProviderNotFoundError
from arvel.logging import Log

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, MutableMapping

    from arvel.foundation.provider import ServiceProvider

    ASGIReceive = Callable[[], Awaitable[MutableMapping[str, object]]]
    ASGISend = Callable[[MutableMapping[str, object]], Awaitable[None]]

logger = Log.named("arvel.foundation.application")


def _apply_early_log_level(config: AppSettings) -> None:
    """Bootstrap minimal logging before providers run.

    ``configure_logging`` (called by ``ObservabilityProvider.boot``) sets up
    the full structlog + stdlib pipeline, but the provider *register* phase
    runs first.  By default structlog uses ``PrintLogger`` which writes
    directly to stdout and ignores stdlib log levels entirely.

    This function switches structlog to stdlib early and sets the root
    logger level so that debug-level provider lifecycle messages are
    filtered correctly.  ``configure_logging`` will overwrite this with the
    full configuration later.
    """
    import logging

    import structlog

    from arvel.observability.config import ObservabilitySettings

    try:
        obs = get_module_settings(config, ObservabilitySettings)
    except (ConfigurationError, KeyError) as exc:
        import structlog

        structlog.get_logger("arvel.foundation.application").warning(
            "early_log_level_settings_fallback",
            error=str(exc),
        )
        obs = ObservabilitySettings()

    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stdout))

    structlog.configure(
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def _install_openapi_security(
    app: FastAPI,
    security_schemes: dict[str, dict[str, Any]],
    global_security: list[dict[str, list[str]]] | None,
) -> None:
    """Patch the FastAPI app's ``openapi()`` to inject security schemes."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            summary=app.summary,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            routes=app.routes,
            tags=app.openapi_tags,
        )

        schema.setdefault("components", {})["securitySchemes"] = security_schemes
        if global_security:
            schema["security"] = global_security

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]


class Application:
    """Arvel application kernel.

    User code should call ``Application.configure(base_path)`` which returns an
    ASGI-compatible object suitable for uvicorn.  The async bootstrap runs
    automatically on the first ASGI event.
    """

    _booted: bool
    _testing: bool
    _boot_lock: anyio.Lock
    _shutdown_lock: anyio.Lock
    _shutting_down: bool
    _shutdown_complete: bool

    def __init__(
        self,
        base_path: Path,
        config: AppSettings,
        container: Container,
        providers: list[ServiceProvider],
        fastapi_app: FastAPI,
    ) -> None:
        self.base_path = base_path
        self.config = config
        self.container = container
        self.providers = providers
        self._fastapi_app = fastapi_app
        self._booted = True
        self._testing = False

    # ── Public API ───────────────────────────────────────────

    @classmethod
    def _new_unbooted(cls, base_path: Path, *, testing: bool) -> Application:
        """Create an unbooted instance with all fields initialized."""
        instance = cls.__new__(cls)
        instance.base_path = base_path
        instance._testing = testing
        instance._booted = False
        instance._boot_lock = anyio.Lock()
        instance._shutdown_lock = anyio.Lock()
        instance._shutting_down = False
        instance._shutdown_complete = False
        return instance

    @classmethod
    def configure(
        cls,
        base_path: str | Path = ".",
        *,
        testing: bool = False,
    ) -> Application:
        """Configure an Arvel application (sync, safe for uvicorn factory).

        Returns an ``Application`` that implements the ASGI protocol.  The
        heavy async bootstrap (config loading, provider lifecycle) runs
        automatically on the first ASGI event — not at import time.
        """
        return cls._new_unbooted(Path(base_path).resolve(), testing=testing)

    @classmethod
    async def create(
        cls,
        base_path: str | Path = ".",
        *,
        testing: bool = False,
    ) -> Application:
        """Create and bootstrap an Arvel application eagerly (async).

        Useful for tests or scripts where you need a fully-booted app
        immediately.  For ``arvel serve``, prefer ``configure()``.
        """
        app_instance = cls._new_unbooted(
            Path(base_path).resolve(),  # noqa: ASYNC240
            testing=testing,
        )
        await app_instance._bootstrap(testing=testing)
        return app_instance

    def asgi_app(self) -> FastAPI:
        return self._fastapi_app

    def settings[TModuleSettings: ModuleSettings](
        self,
        settings_type: type[TModuleSettings],
    ) -> TModuleSettings:
        """Return a typed settings slice loaded on this application."""
        if not self._booted:
            raise RuntimeError("Application is not booted yet; settings are unavailable")
        return get_module_settings(self.config, settings_type)

    async def __call__(
        self,
        scope: MutableMapping[str, object],
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        """ASGI interface — lazy-boots on first call, then delegates to FastAPI.

        Exceptions that reach FastAPI's exception handlers are logged once
        there and converted into an HTTP response.  Starlette's
        ``ServerErrorMiddleware`` re-raises after sending that response,
        which causes Uvicorn to log the *same* traceback a second time.
        We absorb the re-raise here so every error produces exactly one
        structured log entry.
        """
        if not self._booted:
            async with self._boot_lock:
                if not self._booted:
                    await self._boot()

        response_started = False
        original_send = send

        async def _track_send(message: MutableMapping[str, object]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await original_send(message)

        try:
            await self._fastapi_app(scope, receive, _track_send)
        except Exception:
            if response_started:
                # Response already sent — exception was handled by our
                # exception_handler and logged via structlog.  Swallow
                # the re-raise to prevent duplicate tracebacks from
                # Uvicorn's ASGI runner.
                return
            raise

    async def shutdown(self) -> None:
        if self._shutdown_complete:
            return

        # FR-013: Safe to call on unbooted app
        if not self._booted:
            self._shutdown_complete = True
            return

        async with self._shutdown_lock:
            if self._shutdown_complete or self._shutting_down:
                return
            self._shutting_down = True

            try:
                for provider in reversed(self.providers):
                    provider_name = type(provider).__name__
                    logger.debug("provider_shutdown_start", provider=provider_name)
                    try:
                        await provider.shutdown(self)
                    except Exception as exc:
                        # FR-021: Log full error message and traceback
                        import traceback as tb

                        logger.error(
                            "provider_shutdown_failed",
                            provider=provider_name,
                            error=type(exc).__name__,
                            error_message=str(exc),
                            traceback=tb.format_exc(),
                        )
                    else:
                        logger.debug("provider_shutdown_ok", provider=provider_name)
            finally:
                await self.container.close()
                self._shutdown_complete = True
                self._shutting_down = False
                logger.info("application_shutdown_complete")

    # ── Internal ─────────────────────────────────────────────

    async def _bootstrap(self, *, testing: bool = False) -> None:
        """Shared async bootstrap — load config, register providers, build container."""
        t_start = time.monotonic()
        base = self.base_path

        config = await load_config(base, testing=testing)
        t_config = time.monotonic()

        _apply_early_log_level(config)

        if str(base) not in sys.path:
            sys.path.insert(0, str(base))

        builder = ContainerBuilder()
        builder.provide_value(AppSettings, config, scope=Scope.APP)
        for settings_type, settings in config._module_settings.items():
            builder.provide_value(settings_type, settings, scope=Scope.APP)

        provider_classes = self._load_providers(base)
        providers = [pc() for pc in provider_classes]
        providers.sort(key=lambda p: p.priority)

        for provider in providers:
            provider.configure(config)

        for provider in providers:
            provider_name = type(provider).__name__
            logger.debug("provider_register_start", provider=provider_name)
            try:
                await provider.register(builder)
            except Exception as exc:
                logger.error(
                    "provider_register_failed",
                    provider=provider_name,
                    error=type(exc).__name__,
                )
                raise BootError(
                    f"Provider {provider_name} failed during register: {exc}",
                    provider_name=provider_name,
                    cause=exc,
                ) from exc
            logger.debug("provider_register_ok", provider=provider_name)

        container = builder.build()
        t_register = time.monotonic()

        self.config = config
        self.container = container
        self.providers = providers
        self._fastapi_app = self._build_fastapi_app(config)

        await self._boot_providers()
        t_boot = time.monotonic()

        self._booted = True
        logger.info(
            "application_booted",
            app_name=config.app_name,
            app_env=config.app_env,
            debug=config.app_debug,
            providers=len(providers),
            config_ms=round((t_config - t_start) * 1000, 1),
            register_ms=round((t_register - t_config) * 1000, 1),
            boot_ms=round((t_boot - t_register) * 1000, 1),
            total_ms=round((t_boot - t_start) * 1000, 1),
        )

    async def _boot(self) -> None:
        """Run the full async bootstrap (provider lifecycle)."""
        await self._bootstrap(testing=self._testing)

    def _build_fastapi_app(self, config: AppSettings) -> FastAPI:
        @asynccontextmanager
        async def _lifespan(_app: FastAPI):
            yield
            await self.shutdown()

        app = FastAPI(
            title=config.app_name,
            lifespan=_lifespan,
            description=config.app_description,
            version=config.app_version,
            summary=config.app_summary or None,
            terms_of_service=config.app_terms_of_service or None,
            contact=config.app_contact,
            license_info=config.app_license_info,
            openapi_tags=config.app_openapi_tags,
            docs_url=config.app_docs_url,
            redoc_url=config.app_redoc_url,
            openapi_url=config.app_openapi_url,
        )

        security_schemes = config.app_openapi_security_schemes
        global_security = config.app_openapi_global_security
        if security_schemes:
            _install_openapi_security(app, security_schemes, global_security)

        if config.app_exception_handlers:
            from arvel.http.exception_handler import install_exception_handlers

            install_exception_handlers(app, debug=config.app_debug)

        return app

    async def _boot_providers(self) -> None:
        booted: list[ServiceProvider] = []
        for provider in self.providers:
            provider_name = type(provider).__name__
            logger.debug("provider_boot_start", provider=provider_name)
            try:
                await provider.boot(self)
            except Exception as exc:
                logger.error(
                    "provider_boot_failed",
                    provider=provider_name,
                    error=type(exc).__name__,
                    error_message=str(exc),
                )
                # FR-009: Rollback already-booted providers in reverse order
                for booted_provider in reversed(booted):
                    bp_name = type(booted_provider).__name__
                    try:
                        await booted_provider.shutdown(self)
                    except Exception as shutdown_exc:
                        logger.warning(
                            "provider_rollback_shutdown_failed",
                            provider=bp_name,
                            error=str(shutdown_exc),
                        )
                await self.container.close()
                raise BootError(
                    f"Provider {provider_name} failed during boot: {exc}",
                    provider_name=provider_name,
                    cause=exc,
                ) from exc
            booted.append(provider)
            logger.debug("provider_boot_ok", provider=provider_name)

    @staticmethod
    def _load_providers(base_path: Path) -> list[type[ServiceProvider]]:
        """Load service providers from ``bootstrap/providers.py``."""
        providers_file = base_path / "bootstrap" / "providers.py"
        if not providers_file.exists():
            msg = "bootstrap/providers.py not found — every Arvel app must define it"
            raise ProviderNotFoundError(msg, module_path=str(providers_file))

        module_key = f"arvel.bootstrap.providers.{base_path.name}"
        spec = importlib.util.spec_from_file_location(module_key, str(providers_file))
        if spec is None or spec.loader is None:
            msg = f"Cannot load {providers_file}"
            raise ProviderNotFoundError(msg, module_path=str(providers_file))

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_key] = module
        spec.loader.exec_module(module)

        provider_list: list[type[ServiceProvider]] | None = getattr(module, "providers", None)
        if provider_list is None:
            msg = "bootstrap/providers.py must define a 'providers' list"
            raise ProviderNotFoundError(msg, module_path=str(providers_file))

        return list(provider_list)

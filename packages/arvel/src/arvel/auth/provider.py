"""AuthServiceProvider — registers auth components into the DI container."""

from __future__ import annotations

import importlib
from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar, cast

from arvel.auth.config import AuthConfig, GuardConfig, ProviderConfig
from arvel.auth.exceptions import AuthConfigError
from arvel.auth.guard import Guard
from arvel.auth.guards.jwt import JwtGuard
from arvel.auth.guards.session import SessionGuard
from arvel.auth.guards.token import TokenGuard
from arvel.auth.manager import AuthManager
from arvel.auth.providers.arvent import ArventUserProvider
from arvel.console._subsystem import CliSubsystem
from arvel.providers.service_provider import ServiceProvider

_MIN_JWT_SECRET_LENGTH = 32


def _import_class(dotted: str) -> type[Any]:
    """Dynamically import a class from a dotted path like ``app.models.user.User``."""
    module_path, _, class_name = dotted.rpartition(".")
    if not module_path:
        msg = f"Invalid dotted class path: {dotted!r}"
        raise AuthConfigError(msg)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name, None)
    if cls is None:
        msg = f"Class {class_name!r} not found in module {module_path!r}."
        raise AuthConfigError(msg)
    return cast("type[Any]", cls)


def _users_provider(config: AuthConfig) -> ProviderConfig | None:
    """Return the first Arvent-backed provider config, or None."""
    for p in config.providers.values():
        if p.driver == "arvent":
            return p
    return None


class AuthServiceProvider(ServiceProvider):
    # Closure pulls in DATABASE automatically (the Arvent provider needs it).
    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.AUTH

    def commands(self) -> list[Any]:
        from arvel.auth.commands import AuthInstallCommand  # noqa: PLC0415

        return [AuthInstallCommand()]

    def register(self) -> None:
        from arvel.auth.gate import Gate  # noqa: PLC0415

        config = self._load_config()
        self._validate_jwt_config(config)
        self._register_manager(config)
        self._register_services(config)
        self.container.singleton(Gate, Gate)
        # Routes must be registered here (not in boot) because
        # Router.register_with_app() is called synchronously during create_asgi()
        # — before the async boot() phase. Any routes added after that call are
        # invisible to FastAPI.
        if config.routes.enabled:
            self._mount_routes(config)

    async def boot(self) -> None:
        self._publish_migrations()
        self._publish_config()
        self._publish_views()
        self._publish_routes()
        self._wire_ev_service()
        self._attach_default_listeners()

    def _wire_ev_service(self) -> None:
        from arvel.auth.email_verification_service import EmailVerificationService  # noqa: PLC0415
        from arvel.auth.listeners import _set_ev_service  # noqa: PLC0415

        if self.container.bound(EmailVerificationService):
            _set_ev_service(self.container.make(EmailVerificationService))

    # ─── publish helpers ────────────────────────────────────────────────────

    def _publish_migrations(self) -> None:
        from arvel.auth import migrations as auth_migrations  # noqa: PLC0415

        stub_dir = Path(auth_migrations.__file__).parent
        self.publishes(
            {
                stub_dir / "create_users_table.py": "database/migrations",
                stub_dir / "create_refresh_tokens_table.py": "database/migrations",
                stub_dir / "create_personal_access_tokens_table.py": "database/migrations",
            },
            tag="arvel-auth-migrations",
            is_migrations=True,
        )

    def _publish_config(self) -> None:
        from arvel.auth import stubs as auth_stubs  # noqa: PLC0415

        stub_dir = Path(auth_stubs.__file__).parent
        self.publishes(
            {stub_dir / "config_auth.py": "config/auth.py"},
            tag="arvel-auth-config",
        )

    def _publish_views(self) -> None:
        from arvel.auth import stubs as auth_stubs  # noqa: PLC0415

        views_src = Path(auth_stubs.__file__).parent / "views"
        emails_src = views_src / "auth" / "emails"
        self.publishes(
            {
                views_src / "layouts" / "base.html.j2": "templates/layouts/base.html.j2",
                emails_src / "verify_email.html.j2": "templates/auth/emails/verify_email.html.j2",
                emails_src / "verify_email.txt.j2": "templates/auth/emails/verify_email.txt.j2",
                emails_src
                / "password_reset.html.j2": "templates/auth/emails/password_reset.html.j2",
                emails_src / "password_reset.txt.j2": "templates/auth/emails/password_reset.txt.j2",
            },
            tag="arvel-auth-views",
        )

    def _publish_routes(self) -> None:
        from arvel.auth import stubs as auth_stubs  # noqa: PLC0415

        stub_dir = Path(auth_stubs.__file__).parent
        self.publishes(
            {stub_dir / "routes_auth.py": "routes/auth.py"},
            tag="arvel-auth-routes",
        )

    def _attach_default_listeners(self) -> None:
        from arvel.auth.events import PasswordResetRequested, Registered  # noqa: PLC0415
        from arvel.auth.listeners import (  # noqa: PLC0415
            SendPasswordResetEmail,
            SendVerificationEmail,
        )
        from arvel.events.dispatcher import EventDispatcher  # noqa: PLC0415

        if not self.container.bound(EventDispatcher):
            return

        dispatcher = self.container.make(EventDispatcher)
        # Only register defaults when the app hasn't wired its own listeners.
        # Apps that need custom email composition register their listeners in
        # their own ServiceProvider.register(), which runs before boot().
        if not dispatcher.listeners(Registered):
            dispatcher.listen(Registered, SendVerificationEmail)
        if not dispatcher.listeners(PasswordResetRequested):
            dispatcher.listen(PasswordResetRequested, SendPasswordResetEmail)

    # ─── internal ──────────────────────────────────────────────────────────

    def _load_config(self) -> AuthConfig:
        """Build an AuthConfig from the loaded ``config/auth.py`` module.

        If an ``AuthConfig`` is already bound in the container (e.g. in tests),
        it's used directly. Otherwise we pull every field from the config module
        via the dotted-key lookup registry and validate with Pydantic.
        """
        from arvel.config._lookup_registry import ConfigKeyError, lookup  # noqa: PLC0415

        if self.container.bound(AuthConfig):
            return self.container.make(AuthConfig)

        try:
            module = lookup("auth")
        except ConfigKeyError as exc:
            msg = f"No config/auth.py found. {exc}"
            raise AuthConfigError(msg) from exc

        # Build a plain dict from module-level attributes, then let Pydantic
        # validate and coerce each field (guards, providers, etc. are raw dicts).
        fields = (
            "default",
            "guards",
            "providers",
            "hash",
            "jwt",
            "refresh",
            "routes",
            "rate_limit",
        )
        data: dict[str, object] = {}
        for field in fields:
            val = getattr(module, field, None)
            if val is not None:
                data[field] = val

        return AuthConfig.model_validate(data)

    @staticmethod
    def _validate_jwt_config(config: AuthConfig) -> None:
        secret_length = len(config.jwt.secret)
        if secret_length < _MIN_JWT_SECRET_LENGTH:
            msg = "jwt.secret must be at least 32 characters"
            raise AuthConfigError(msg)
        if config.jwt.algorithm.lower() == "none":
            msg = "jwt.algorithm must not be 'none'"
            raise AuthConfigError(msg)

    def build_manager(self, config: AuthConfig) -> AuthManager:
        """Build and return an ``AuthManager`` from ``config`` (without binding it)."""
        guards: dict[str, Guard] = {}
        for name, guard_cfg in config.guards.items():
            guards[name] = self._build_guard(guard_cfg, config)  # type: ignore[assignment]
        return AuthManager(guards=guards, default=config.default)

    def _register_manager(self, config: AuthConfig) -> None:
        """Register the AuthManager guard system for request-level identity.

        This handles ``Auth::user()``-style lookups — attaching the current
        user to ``request.state.user`` via ``OptionalAuthenticate``. It's
        complementary to ``AuthService``, which handles auth *flows* (login,
        register, refresh).
        """
        manager = self.build_manager(config)
        self.container.instance(AuthManager, manager)

        from arvel.facades.auth import Auth  # noqa: PLC0415

        Auth.set_manager(manager)

    def _register_services(self, config: AuthConfig) -> None:
        """Register AuthService, PasswordService, EmailVerificationService, AuthController."""
        from arvel.auth.auth_service import AuthService  # noqa: PLC0415
        from arvel.auth.broker import AuthBroker  # noqa: PLC0415
        from arvel.auth.email_verification_service import EmailVerificationService  # noqa: PLC0415
        from arvel.auth.http.controller import AuthController, CookieConfig  # noqa: PLC0415
        from arvel.auth.http.resources import UserResource  # noqa: PLC0415
        from arvel.auth.password_service import PasswordService  # noqa: PLC0415

        provider_cfg = _users_provider(config)
        user_model_cls: type[Any] | None = None
        user_resource_cls: type[Any] = UserResource

        if provider_cfg is not None:
            user_model_cls = _import_class(provider_cfg.model)
            if provider_cfg.resource:
                user_resource_cls = _import_class(provider_cfg.resource)

        jwt = config.jwt
        refresh = config.refresh

        broker_cls: type[AuthService] = (
            _import_class(config.broker_class) if config.broker_class else AuthBroker
        )
        auth_service = broker_cls(
            jwt=jwt,
            refresh_ttl=timedelta(seconds=refresh.ttl_seconds),
            user_model=user_model_cls,
        )
        password_service = PasswordService(user_model=user_model_cls)
        email_verification_service = EmailVerificationService(
            secret=jwt.secret,
            user_model=user_model_cls,
        )
        controller = AuthController(
            auth=auth_service,
            passwords=password_service,
            email_verification=email_verification_service,
            cookies=CookieConfig(
                refresh_cookie=refresh.cookie_name,
                csrf_cookie=refresh.csrf_cookie_name,
                refresh_ttl_seconds=refresh.ttl_seconds,
                secure=refresh.cookie_secure,
                user_resource_class=user_resource_cls,
            ),
        )

        self.container.instance(AuthService, auth_service)
        self.container.instance(PasswordService, password_service)
        self.container.instance(EmailVerificationService, email_verification_service)
        self.container.instance(AuthController, controller)
        self.container.instance(AuthBroker, auth_service)

        from arvel.auth.auth_service import set_current as _bind_current  # noqa: PLC0415

        _bind_current(auth_service)

    def _mount_routes(self, config: AuthConfig) -> None:
        """Register auth endpoints in the framework's Router singleton."""
        from fastapi import Request as FastAPIRequest  # noqa: PLC0415
        from fastapi.responses import Response  # noqa: PLC0415

        from arvel.auth.http.controller import AuthController  # noqa: PLC0415
        from arvel.auth.http.requests import (  # noqa: PLC0415
            ForgotPasswordRequest,
            LoginRequest,
            RegisterRequest,
            ResetPasswordRequest,
        )
        from arvel.http.middleware.database_transaction import DatabaseTransaction  # noqa: PLC0415
        from arvel.routing import Route  # noqa: PLC0415

        ctrl = self.container.make(AuthController)
        p = config.routes.prefix.rstrip("/")
        db_tx = [DatabaseTransaction()]

        async def handle_register(payload: RegisterRequest) -> Any:
            return await ctrl.register(payload)

        async def handle_login(payload: LoginRequest, response: Response) -> Any:
            return await ctrl.login(payload, response)

        async def handle_refresh(request: FastAPIRequest, response: Response) -> Any:
            return await ctrl.refresh(request, response)

        async def handle_logout(request: FastAPIRequest, response: Response) -> Any:
            return await ctrl.logout(request, response)

        async def handle_me(request: FastAPIRequest) -> Any:
            return await ctrl.me(request)

        async def handle_forgot_password(payload: ForgotPasswordRequest) -> Any:
            return await ctrl.forgot_password(payload)

        async def handle_reset_password(payload: ResetPasswordRequest) -> Any:
            return await ctrl.reset_password(payload)

        async def handle_verify_email(signed: str) -> Any:
            return await ctrl.verify_email(signed)

        async def handle_verify_resend(request: FastAPIRequest) -> Any:
            return await ctrl.verify_email_resend(request)

        Route.post(f"{p}/register", name="auth.register", status_code=201, middleware=db_tx)(
            handle_register
        )
        Route.post(f"{p}/login", name="auth.login", middleware=db_tx)(handle_login)
        Route.post(f"{p}/refresh", name="auth.refresh", middleware=db_tx)(handle_refresh)
        Route.post(
            f"{p}/logout",
            name="auth.logout",
            status_code=204,
            response_class=Response,
            response_model=None,
            middleware=db_tx,
        )(handle_logout)
        Route.get(f"{p}/me", name="auth.me", middleware=db_tx)(handle_me)
        Route.post(
            f"{p}/forgot-password",
            name="auth.forgot_password",
            status_code=202,
            middleware=db_tx,
        )(handle_forgot_password)
        Route.post(f"{p}/reset-password", name="auth.reset_password", middleware=db_tx)(
            handle_reset_password
        )
        Route.get(f"{p}/verify/{{signed}}", name="auth.verify_email", middleware=db_tx)(
            handle_verify_email
        )
        Route.post(f"{p}/verify/resend", name="auth.verify_resend", middleware=db_tx)(
            handle_verify_resend
        )

    # ─── guard/provider builders (existing code) ───────────────────────────

    def _build_guard(self, guard_cfg: object, config: object) -> object:
        if not isinstance(guard_cfg, GuardConfig):
            msg = "Guard config must be a GuardConfig instance."
            raise AuthConfigError(msg)

        driver = guard_cfg.driver
        if driver == "session":
            provider = self._build_provider(guard_cfg.provider, config)
            return SessionGuard(resolver=provider)  # type: ignore[arg-type]
        if driver == "jwt":
            provider = self._build_provider(guard_cfg.provider, config)
            if not isinstance(config, AuthConfig):
                msg = "Guard config must be an AuthConfig instance for JWT driver."
                raise AuthConfigError(msg)
            return JwtGuard(
                resolver=provider,  # type: ignore[arg-type]
                jwt=config.jwt,
            )
        if driver == "token":
            token_repo = self.app.make("auth.token_repository")
            user_repo = self.app.make("auth.user_repository")
            return TokenGuard(token_repository=token_repo, user_repository=user_repo)
        msg = f"Unknown auth guard driver: '{driver}'."
        raise AuthConfigError(msg)

    def _build_provider(self, provider_name: str, config: object) -> object:
        if not isinstance(config, AuthConfig):
            msg = "config must be AuthConfig."
            raise AuthConfigError(msg)

        provider_cfg = config.providers.get(provider_name)
        if provider_cfg is None:
            msg = f"Auth provider '{provider_name}' is not configured."
            raise AuthConfigError(msg)

        if provider_cfg.driver == "arvent":
            parts = provider_cfg.model.rsplit(".", 1)
            mod = importlib.import_module(parts[0])
            model_class = getattr(mod, parts[1])
            return ArventUserProvider(model=model_class)
        msg = f"Unknown auth provider driver: '{provider_cfg.driver}'. Valid drivers: 'arvent'."
        raise AuthConfigError(msg)

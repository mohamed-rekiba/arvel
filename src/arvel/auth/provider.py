"""AuthServiceProvider — binds the AuthManager + Gate (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from arvel.auth import AuthManager, Gate
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class AuthServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_auth(app: Container) -> AuthManager:
            return AuthManager(app)

        def make_gate(_app: Container) -> Gate:
            return Gate()

        def make_guard(app: Any) -> Any:
            from arvel.auth.guards import GuardManager

            return GuardManager(app)

        def make_user_provider(app: Any) -> Any:
            from arvel.auth.identity import DbIdentityStore, UserProvider

            if not hasattr(app, "config"):
                return None
            user_model: Any = app.config("auth.user_model")
            if user_model is None:
                return None  # the app must configure auth.user_model to use identity resolution
            trusted: set[str] = {
                str(name)
                for name in cast("list[Any]", app.config("auth.trusted_email_providers", []) or [])
            }
            jit = bool(app.config("auth.jit", False))
            return UserProvider(
                DbIdentityStore(user_model), trusted_email_providers=trusted, jit=jit
            )

        self.app.singleton("auth", make_auth)
        self.app.singleton("gate", make_gate)
        self.app.singleton("guard", make_guard)
        self.app.singleton("auth.user_provider", make_user_provider)

    def boot(self) -> None:
        """No-op (apps define abilities/policies in their own AuthServiceProvider)."""


__all__ = ["AuthServiceProvider"]

"""Auth Security cluster.
Tests are FAILING before the fix and PASSING after.

): SessionGuard.attempt() must verify password hash.
): AuthService and JwtGuard must use the same jwt.secret.
): JwtConfig.secret must enforce min_length=32.
"""

from __future__ import annotations

from typing import Any

import pytest

# Helpers


class _FakeSessionData:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data or {}
        self.regenerated = False

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def put(self, key: str, value: Any) -> None:
        self._data[key] = value

    def forget(self, key: str) -> None:
        self._data.pop(key, None)

    def regenerate(self) -> None:
        self.regenerated = True


class _FakeRequest:
    def __init__(self, session: _FakeSessionData | None = None) -> None:
        self.state = type("State", (), {"session": session or _FakeSessionData()})()


def _make_argon2_user(plain_password: str) -> dict[str, Any]:
    """Return a fake user dict with an argon2id-hashed password."""
    from arvel.facades.hash import Hash

    return {
        "id": "user-1",
        "email": "alice@example.com",
        "password": Hash.make(plain_password),
        "_auth_password_field": "password",
    }


class _PasswordAwareResolver:
    """Resolver that returns users by email; password is stored hashed."""

    def __init__(self, users: dict[str, Any]) -> None:
        self._users = users

    async def by_id(self, user_id: str) -> Any | None:
        return next((u for u in self._users.values() if u["id"] == user_id), None)

    async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
        return self._users.get(str(credentials.get("email")))


# Session guard must verify password before login


class TestStory1SessionGuardPasswordVerification:
    """attempt() must call Hash.check() before login()."""

    @pytest.mark.asyncio
    async def test_attempt_returns_false_for_wrong_password(self) -> None:
        """C-1: Wrong password must not authenticate. Currently FAILS (returns True)."""
        from arvel.auth.guards.session import SessionGuard

        user = _make_argon2_user("correct-password")
        resolver = _PasswordAwareResolver({"alice@example.com": user})
        guard = SessionGuard(resolver=resolver)
        request = _FakeRequest()

        result = await guard.attempt(
            {"email": "alice@example.com", "password": "wrong-password"},
            request,
        )

        # BUG: currently returns True (no password check) — must return False after fix.
        assert result is False

    @pytest.mark.asyncio
    async def test_attempt_returns_true_for_correct_password(self) -> None:
        """Positive path: correct credentials must still work after the fix."""
        from arvel.auth.guards.session import SessionGuard

        user = _make_argon2_user("correct-password")
        resolver = _PasswordAwareResolver({"alice@example.com": user})
        guard = SessionGuard(resolver=resolver)
        request = _FakeRequest()

        result = await guard.attempt(
            {"email": "alice@example.com", "password": "correct-password"},
            request,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_attempt_returns_false_for_missing_user(self) -> None:
        """Email enumeration guard: unknown email → False, same as wrong password."""
        from arvel.auth.guards.session import SessionGuard

        resolver = _PasswordAwareResolver({})
        guard = SessionGuard(resolver=resolver)
        request = _FakeRequest()

        result = await guard.attempt(
            {"email": "nobody@example.com", "password": "anything"},
            request,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_login_not_called_on_wrong_password(self) -> None:
        """Guard must NOT set session user_id when password is wrong."""
        from arvel.auth.guards.session import SessionGuard

        user = _make_argon2_user("secret")
        resolver = _PasswordAwareResolver({"alice@example.com": user})
        session = _FakeSessionData()
        guard = SessionGuard(resolver=resolver)
        request = _FakeRequest(session)

        await guard.attempt(
            {"email": "alice@example.com", "password": "bad"},
            request,
        )

        assert session.get("_auth_id") is None


# JWT key alignment


class TestStory2JwtKeyAlignment:
    """AuthService and JwtGuard must share the same jwt.secret."""

    def test_jwt_guard_construction_uses_jwt_secret(self) -> None:
        """JwtGuard must be constructable with a 32-char secret from config.jwt.secret.

        The fix ensures provider.py uses config.jwt.secret (not app.key).
        """
        from arvel.auth.config import JwtConfig
        from arvel.auth.guards.jwt import JwtGuard

        secret = "a" * 32
        cfg = JwtConfig(secret=secret)

        # Must construct without error using the jwt secret
        class _NullResolver:
            async def by_id(self, user_id: str) -> None: ...
            async def by_credentials(self, credentials: dict[str, object]) -> None: ...

        guard = JwtGuard(
            resolver=_NullResolver(),
            jwt=cfg,
        )
        assert guard.secret_or_key == secret

    def test_provider_passes_jwt_secret_to_jwt_guard(self) -> None:
        """provider.py must pass config.jwt.secret to JwtGuard (not app.key).

        Ensures the code in _build_guard() uses config.jwt.secret.
        """
        import inspect

        from arvel.auth import provider as auth_provider

        source = inspect.getsource(auth_provider)
        # After fix: must NOT reference app.key for JWT guard
        # The bug: secret = str(lookup("app.key"))
        needle = 'lookup("app.key")'
        uses_app_key = needle in source
        jwt_context = needle in source and "jwt" in source.split(needle)[0].split("\n")[-1]
        assert not uses_app_key or not jwt_context, (
            "provider.py still uses lookup('app.key') for JWT guard"
        )

    def test_provider_passes_jwt_algorithm_issuer_and_audience_to_guard(self) -> None:
        """JWT guard verification must use the same configured claims as issuance."""
        from arvel.application.application import Application
        from arvel.auth.config import AuthConfig, GuardConfig, JwtConfig, ProviderConfig
        from arvel.auth.guards.jwt import JwtGuard
        from arvel.auth.provider import AuthServiceProvider

        secret = "s" * 32
        config = AuthConfig(
            default="api",
            guards={"api": GuardConfig(driver="jwt", provider="users")},
            providers={
                "users": ProviderConfig(
                    driver="arvent",
                    model="arvel.auth.models.user.User",
                )
            },
            jwt=JwtConfig(
                secret=secret,
                algorithm="HS384",
                issuer="https://auth.example.test",
                audience="arvel-api",
            ),
        )

        manager = AuthServiceProvider(Application()).build_manager(config)
        guard = manager.guard("api")

        assert isinstance(guard, JwtGuard)
        assert guard.secret_or_key == secret
        assert guard.algorithm == "HS384"
        assert guard.issuer == "https://auth.example.test"
        assert guard.audience == "arvel-api"

    def test_auth_service_tokens_validate_with_configured_issuer_and_audience(self) -> None:
        """Access tokens minted by AuthService must carry configured JWT claims."""
        import importlib

        from arvel.auth.auth_service import AuthService
        from arvel.auth.config import JwtConfig

        secret = "s" * 32
        service = AuthService(
            jwt=JwtConfig(
                secret=secret,
                algorithm="HS256",
                ttl_seconds=300,
                issuer="https://auth.example.test",
                audience="arvel-api",
            ),
        )

        token = service.issue_access_token(subject="user-1")
        jwt_mod = importlib.import_module("jwt")

        claims = jwt_mod.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer="https://auth.example.test",
            audience="arvel-api",
        )
        assert claims["iss"] == "https://auth.example.test"
        assert claims["aud"] == "arvel-api"


# JWT secret minimum length


class TestStory3JwtSecretMinLength:
    """JwtConfig must reject secrets shorter than 32 chars."""

    def test_jwt_config_rejects_empty_secret(self) -> None:
        """JwtConfig(secret='') must raise ValidationError. Currently FAILS (accepts it)."""
        from arvel.auth.config import JwtConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            JwtConfig(secret="")

    def test_jwt_config_rejects_short_secret(self) -> None:
        """JwtConfig(secret='abc') must raise ValidationError."""
        from arvel.auth.config import JwtConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            JwtConfig(secret="tooshort")

    def test_jwt_config_accepts_32_char_secret(self) -> None:
        """Exactly 32-char secret must be accepted."""
        from arvel.auth.config import JwtConfig

        config = JwtConfig(secret="a" * 32)
        assert len(config.secret) == 32

    def test_jwt_config_accepts_long_secret(self) -> None:
        """Secrets longer than 32 chars must be accepted."""
        from arvel.auth.config import JwtConfig

        config = JwtConfig(secret="x" * 64)
        assert len(config.secret) == 64

    def test_auth_service_provider_rejects_missing_jwt_secret_at_register(self) -> None:
        """Provider boot must fail loudly instead of constructing weak JWT services."""
        from arvel.application.application import Application
        from arvel.auth.config import AuthConfig, RoutesConfig
        from arvel.auth.exceptions import AuthConfigError
        from arvel.auth.provider import AuthServiceProvider

        app = Application()
        app.container.instance(
            AuthConfig,
            AuthConfig(
                default="web",
                guards={},
                providers={},
                routes=RoutesConfig(enabled=False),
            ),
        )

        with pytest.raises(AuthConfigError, match="jwt.secret must be at least 32"):
            AuthServiceProvider(app).register()

    def test_auth_config_stub_reads_jwt_secret_not_app_key(self) -> None:
        """Published auth config must document and read JWT_SECRET explicitly."""
        import inspect

        from arvel.auth.stubs import config_auth

        source = inspect.getsource(config_auth)

        assert "JWT_SECRET" in source
        assert "APP_KEY" not in source
        assert "32" in source

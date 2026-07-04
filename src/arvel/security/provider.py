"""SecurityServiceProvider — binds hash/encrypter/signer (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from arvel.kernel import config
from arvel.kernel.service_provider import ServiceProvider
from arvel.security import Encrypter, Hasher, Signer

if TYPE_CHECKING:
    from arvel.contracts import Container
    from arvel.security.hashing import DriverName


def _require_key() -> str:
    key = config("app.key")
    if not key:
        raise RuntimeError(
            "APP_KEY is not set (config 'app.key'); generate one to use crypto/signing."
        )
    return str(key)


class SecurityServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_hasher(_app: Container) -> Hasher:
            driver = cast("DriverName", config("hashing.driver", "argon2id"))
            options = cast("dict[str, int]", config("hashing.options", {}) or {})
            return Hasher(driver, **options)

        def make_encrypter(_app: Container) -> Encrypter:
            return Encrypter(_require_key())

        def make_signer(_app: Container) -> Signer:
            return Signer(_require_key())

        self.app.singleton("hash", make_hasher)
        self.app.singleton("encrypter", make_encrypter)
        self.app.singleton("signer", make_signer)

    def boot(self) -> None:
        """No-op."""

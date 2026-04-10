"""Password hashing drivers — bcrypt and argon2."""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.security.contracts import HasherContract
from arvel.security.exceptions import HashingError


class BcryptHasher(HasherContract):
    """Bcrypt password hasher. Default cost factor: 12."""

    def __init__(self, *, rounds: int = 12) -> None:
        self._rounds = rounds

    def make(self, password: str) -> str:
        try:
            import bcrypt
        except ImportError as e:
            raise HashingError("bcrypt is not installed: pip install bcrypt") from e

        password_bytes = password.encode("utf-8")
        if len(password_bytes) > 72:
            raise HashingError("Password exceeds bcrypt's 72-byte limit")

        salt = bcrypt.gensalt(rounds=self._rounds)
        return bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    def check(self, password: str, hashed: str) -> bool:
        try:
            import bcrypt
        except ImportError as e:
            raise HashingError("bcrypt is not installed: pip install bcrypt") from e

        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    def needs_rehash(self, hashed: str) -> bool:
        if not hashed.startswith("$2"):
            return True
        try:
            cost = int(hashed.split("$")[2])
        except IndexError, ValueError:
            return True
        return cost != self._rounds


class Argon2Hasher(HasherContract):
    """Argon2id password hasher with OWASP-recommended defaults."""

    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
    ) -> None:
        self._time_cost = time_cost
        self._memory_cost = memory_cost
        self._parallelism = parallelism

    def _get_hasher(self) -> Any:
        try:
            from argon2 import PasswordHasher

            return PasswordHasher(
                time_cost=self._time_cost,
                memory_cost=self._memory_cost,
                parallelism=self._parallelism,
            )
        except ImportError as e:
            raise HashingError("argon2-cffi is not installed: pip install argon2-cffi") from e

    def make(self, password: str) -> str:
        hasher = self._get_hasher()
        return hasher.hash(password)

    def check(self, password: str, hashed: str) -> bool:
        try:
            from argon2.exceptions import VerificationError, VerifyMismatchError
        except ImportError as e:
            raise HashingError("argon2-cffi is not installed: pip install argon2-cffi") from e

        hasher = self._get_hasher()
        try:
            return hasher.verify(hashed, password)
        except VerifyMismatchError, VerificationError:
            return False

    def needs_rehash(self, hashed: str) -> bool:
        hasher = self._get_hasher()
        return hasher.check_needs_rehash(hashed)


class HashManager:
    """Facade that delegates to the configured hashing driver."""

    _drivers: ClassVar[dict[str, type[HasherContract]]] = {
        "bcrypt": BcryptHasher,
        "argon2": Argon2Hasher,
    }

    def __init__(self, driver: str = "bcrypt", **kwargs: Any) -> None:
        cls = self._drivers.get(driver)
        if cls is None:
            available = list(self._drivers)
            raise HashingError(f"Unknown hashing driver: {driver}. Available: {available}")
        self._hasher: HasherContract = cls(**kwargs)
        self._driver_name = driver

    @property
    def driver(self) -> str:
        return self._driver_name

    def make(self, password: str) -> str:
        return self._hasher.make(password)

    def check(self, password: str, hashed: str) -> bool:
        return self._hasher.check(password, hashed)

    def needs_rehash(self, hashed: str) -> bool:
        return self._hasher.needs_rehash(hashed)

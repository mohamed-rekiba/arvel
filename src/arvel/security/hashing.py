"""arvel.security.hashing — driver-based password hashing.

``HashDriver`` is a typed Protocol (``make``/``check``/``needs_rehash``/``info``); two concrete
drivers implement it directly over their underlying crypto packages (no pwdlib indirection):
``Argon2Driver`` (argon2-cffi) and ``BcryptDriver`` (the ``bcrypt`` package). ``needs_rehash``
never takes plaintext — it inspects the stored hash's own parameters, so a caller can decide to
upgrade a hash without ever holding the password again.

``HashManager`` (re-exported as ``Hasher``) ties a *configured* driver (used by ``make`` and as
the ``needs_rehash`` baseline) to format-based auto-detection for ``check``/``info``/``is_hashed``
— so a hash produced by the *other* driver still verifies during a bcrypt→argon2id migration
(AC 4), while ``needs_rehash`` correctly flags it for upgrade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

import argon2
import bcrypt
from argon2.exceptions import InvalidHashError, VerificationError

if TYPE_CHECKING:
    from collections.abc import Callable

DriverName = Literal["argon2id", "bcrypt"]


@dataclass(frozen=True, slots=True)
class HashInfo:
    """The algorithm + cost params a hash was produced with (read from the hash, not a plaintext)."""

    algorithm: str
    options: dict[str, int]


class HashDriver(Protocol):
    """A password-hashing driver — ``needs_rehash``/``info`` are plaintext-free by contract."""

    def make(self, plain: str) -> str: ...
    def check(self, plain: str, hashed: str) -> bool: ...
    def needs_rehash(self, hashed: str) -> bool: ...
    def info(self, hashed: str) -> HashInfo | None: ...


class Argon2Driver:
    """Argon2id via argon2-cffi — arvel's default (stronger than the bcrypt default)."""

    algorithm: Literal["argon2id"] = "argon2id"

    def __init__(
        self, *, memory_cost: int = 65536, time_cost: int = 3, parallelism: int = 4
    ) -> None:
        self._options = {
            "memory_cost": memory_cost,
            "time_cost": time_cost,
            "parallelism": parallelism,
        }
        self._hasher = argon2.PasswordHasher(
            memory_cost=memory_cost, time_cost=time_cost, parallelism=parallelism
        )

    def make(self, plain: str) -> str:
        return self._hasher.hash(plain)

    def check(self, plain: str, hashed: str) -> bool:
        # VerificationError is VerifyMismatchError's base: wrong password, corrupt hash, and
        # any other verification failure all mean "not authenticated", never an exception.
        try:
            return self._hasher.verify(hashed, plain)
        except VerificationError, InvalidHashError:
            return False

    def needs_rehash(self, hashed: str) -> bool:
        # argon2-cffi compares the hash's own embedded params against *this* hasher's configured
        # params — plaintext never enters the comparison.
        try:
            return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError:
            return True

    def info(self, hashed: str) -> HashInfo | None:
        try:
            params = argon2.extract_parameters(hashed)
        except InvalidHashError:
            return None
        return HashInfo(
            algorithm=self.algorithm,
            options={
                "memory_cost": params.memory_cost,
                "time_cost": params.time_cost,
                "parallelism": params.parallelism,
            },
        )

    @staticmethod
    def recognizes(hashed: str) -> bool:
        return hashed.startswith(("$argon2id$", "$argon2i$", "$argon2d$"))


class BcryptDriver:
    """Bcrypt via the ``bcrypt`` package — parity + migration interop with the default."""

    algorithm: Literal["bcrypt"] = "bcrypt"

    def __init__(self, *, rounds: int = 12) -> None:
        self._rounds = rounds

    def make(self, plain: str) -> str:
        # bcrypt only reads the first 72 bytes; bcrypt>=4 rejects longer input instead of
        # silently truncating — truncate explicitly so registration never 500s
        return bcrypt.hashpw(plain.encode()[:72], bcrypt.gensalt(rounds=self._rounds)).decode()

    def check(self, plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode()[:72], hashed.encode())
        except ValueError:
            return False

    def needs_rehash(self, hashed: str) -> bool:
        cost = self._extract_cost(hashed)
        return cost is None or cost != self._rounds

    def info(self, hashed: str) -> HashInfo | None:
        cost = self._extract_cost(hashed)
        if cost is None:
            return None
        return HashInfo(algorithm=self.algorithm, options={"rounds": cost})

    @staticmethod
    def _extract_cost(hashed: str) -> int | None:
        # format: "$2b$NN$<22-char salt><31-char digest>" — NN is the zero-padded cost factor.
        parts = hashed.split("$")
        if len(parts) < 4 or not parts[1].startswith("2"):
            return None
        try:
            return int(parts[2])
        except ValueError:
            return None

    @staticmethod
    def recognizes(hashed: str) -> bool:
        return hashed.startswith(("$2a$", "$2b$", "$2y$"))


_RECOGNIZERS: dict[DriverName, Callable[[str], bool]] = {
    "argon2id": Argon2Driver.recognizes,
    "bcrypt": BcryptDriver.recognizes,
}


class HashManager:
    """Hash driver manager. ``make`` uses the configured driver;
    ``check``/``info``/``is_hashed`` auto-detect the hash's own driver by format; ``needs_rehash``
    is True whenever the hash isn't the *configured* driver+params (never taking plaintext)."""

    def __init__(self, driver: DriverName = "argon2id", **options: int) -> None:
        self._driver_name: DriverName = driver
        self._configured: HashDriver = (
            Argon2Driver(**options) if driver == "argon2id" else BcryptDriver(**options)
        )
        # default-params instances of every known driver, used only to recognize/verify/inspect a
        # hash by its own format — a hash's params are read from the hash, never from these.
        self._by_name: dict[DriverName, HashDriver] = {
            "argon2id": Argon2Driver(),
            "bcrypt": BcryptDriver(),
        }

    def _detect_name(self, hashed: str) -> DriverName | None:
        if not hashed:  # a NULL/empty DB value must fail auth, not raise
            return None
        for name, recognizes in _RECOGNIZERS.items():
            if recognizes(hashed):
                return name
        return None

    def make(self, plain: str) -> str:
        return self._configured.make(plain)

    async def make_async(self, plain: str) -> str:
        """``make`` off the event loop — argon2/bcrypt are CPU-bound; run them in a worker thread
        so hashing on an async request/worker path doesn't block the loop."""
        from anyio.to_thread import run_sync

        return await run_sync(self.make, plain)

    def check(self, plain: str, hashed: str) -> bool:
        name = self._detect_name(hashed)
        if name is None:
            return False
        return self._by_name[name].check(plain, hashed)

    async def check_async(self, plain: str, hashed: str) -> bool:
        """``check`` off the event loop (see :meth:`make_async`)."""
        from anyio.to_thread import run_sync

        return await run_sync(self.check, plain, hashed)

    def needs_rehash(self, hashed: str) -> bool:
        if self._detect_name(hashed) != self._driver_name:
            return True
        return self._configured.needs_rehash(hashed)

    def is_hashed(self, value: str) -> bool:
        return self._detect_name(value) is not None

    def info(self, hashed: str) -> HashInfo | None:
        name = self._detect_name(hashed)
        if name is None:
            return None
        return self._by_name[name].info(hashed)


__all__ = ["Argon2Driver", "BcryptDriver", "DriverName", "HashDriver", "HashInfo", "HashManager"]

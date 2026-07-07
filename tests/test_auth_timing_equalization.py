"""Unknown identifiers must cost exactly one hash verification, like known ones —
no username enumeration by response timing."""

from __future__ import annotations

from arvel.auth.guards import LocalGuard


class SpyHasher:
    def __init__(self) -> None:
        self.checks: list[tuple[str, str]] = []
        self.makes: list[str] = []

    def make(self, plain: str) -> str:
        self.makes.append(plain)
        return f"hashed::{plain}"

    async def make_async(self, plain: str) -> str:
        return self.make(plain)

    def check(self, plain: str, hashed: str) -> bool:
        self.checks.append((plain, hashed))
        return hashed == f"hashed::{plain}"

    async def check_async(self, plain: str, hashed: str) -> bool:
        return self.check(plain, hashed)

    def needs_rehash(self, hashed: str) -> bool:
        return False


async def _lookup(identifier: str) -> str | None:
    return "hashed::right" if identifier == "known@x" else None


async def test_unknown_identifier_still_performs_one_verification() -> None:
    spy = SpyHasher()
    guard = LocalGuard(_lookup, hasher=spy)
    assert await guard.attempt("ghost@x", "whatever") is None
    assert len(spy.checks) == 1  # dummy verification happened
    assert spy.checks[0][1].startswith("hashed::")  # against a real-format digest


async def test_known_identifier_wrong_password_also_one_verification() -> None:
    spy = SpyHasher()
    guard = LocalGuard(_lookup, hasher=spy)
    assert await guard.attempt("known@x", "wrong") is None
    assert len(spy.checks) == 1


async def test_successful_attempt_unchanged() -> None:
    spy = SpyHasher()
    guard = LocalGuard(_lookup, hasher=spy)
    principal = await guard.attempt("known@x", "right")
    assert principal is not None and principal.subject == "known@x"


async def test_dummy_digest_is_cached_across_attempts() -> None:
    spy = SpyHasher()
    guard = LocalGuard(_lookup, hasher=spy)
    await guard.attempt("ghost@x", "a")
    await guard.attempt("ghost2@x", "b")
    assert len(spy.makes) == 1  # one dummy make, reused
    assert len(spy.checks) == 2


# --- the same equalization must hold at the AuthManager.attempt level, where the unknown-user
#     short-circuit previously skipped verification entirely (enumeration oracle). --------------


class _App:
    def __init__(self, bindings: dict[str, object]) -> None:
        self._b = bindings

    def make(self, key: str) -> object:
        return self._b[key]

    def bound(self, key: str) -> bool:
        return key in self._b


class _User:
    def __init__(self, password: str) -> None:
        self._password = password

    def get_auth_password(self) -> str:
        return self._password


async def test_manager_attempt_unknown_user_still_verifies() -> None:
    from arvel.auth import AuthManager
    from arvel.kernel.globals import set_application

    spy = SpyHasher()
    set_application(_App({"hash": spy}))
    try:

        async def provider(_credentials: dict[str, str]) -> None:
            return None  # unknown identifier

        ok = await AuthManager().attempt(
            {"email": "ghost@x", "password": "pw"}, provider
        )
        assert ok is False
        assert len(spy.checks) == 1  # dummy burn happened at the manager level, not skipped
    finally:
        set_application(None)


async def test_manager_attempt_known_wrong_password_verifies_once() -> None:
    from arvel.auth import AuthManager
    from arvel.kernel.globals import set_application

    spy = SpyHasher()
    set_application(_App({"hash": spy}))
    try:

        async def provider(_credentials: dict[str, str]) -> _User:
            return _User("hashed::right")

        ok = await AuthManager().attempt(
            {"email": "known@x", "password": "wrong"}, provider
        )
        assert ok is False
        assert len(spy.checks) == 1  # same single verification as the unknown path
    finally:
        set_application(None)

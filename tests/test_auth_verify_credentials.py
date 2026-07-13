"""Security — ``verify_credentials`` timing equalization.

An unknown user must cost the same as a wrong password: exactly ONE hash verification on both
paths, so response time can't be used to enumerate valid identifiers. These tests assert the
count directly (a fake hasher records every check) rather than relying on wall-clock timing.
"""

from __future__ import annotations

from typing import Any

import arvel.auth as auth_mod
from arvel.auth import verify_credentials


class _CountingHasher:
    """Records make/check calls so the test can assert exactly one verify per attempt.

    ``make_async(p)`` → ``"hash::p"``; ``check_async(p, h)`` is True iff ``h`` is that hash of ``p``
    — i.e. it verifies the *plaintext* against the stored hash, like a real hasher."""

    def __init__(self) -> None:
        self.checks: list[tuple[str, str]] = []
        self.makes: list[str] = []

    async def make_async(self, plain: str) -> str:
        self.makes.append(plain)
        return f"hash::{plain}"

    async def check_async(self, plain: str, hashed: str) -> bool:
        self.checks.append((plain, hashed))
        return hashed == f"hash::{plain}"


class _User:
    def __init__(self, hashed: str) -> None:
        self._hashed = hashed

    def get_auth_password(self) -> Any:
        return self._hashed


def _reset_dummy() -> None:
    # the cached process-wide dummy digest is module state; clear it so each test starts clean
    auth_mod._dummy_hash = None


async def test_known_wrong_password_runs_exactly_one_verify() -> None:
    _reset_dummy()
    h = _CountingHasher()
    user = _User("hash::right")
    assert await verify_credentials(user, "wrong", hasher=h) is False
    assert len(h.checks) == 1  # one verify, against the stored hash
    assert h.checks[0] == ("wrong", "hash::right")


async def test_unknown_user_runs_exactly_one_verify_against_dummy() -> None:
    _reset_dummy()
    h = _CountingHasher()
    assert await verify_credentials(None, "wrong", hasher=h) is False
    # exactly one verify, against the dummy digest — same cost as the known-wrong path above
    assert len(h.checks) == 1
    assert h.checks[0][0] == "wrong"
    assert h.checks[0][1].startswith("hash::")  # the dummy digest, not a real user's hash


async def test_correct_password_authenticates() -> None:
    _reset_dummy()
    h = _CountingHasher()
    user = _User("hash::right")
    assert await verify_credentials(user, "right", hasher=h) is True
    assert len(h.checks) == 1


async def test_user_with_empty_stored_hash_still_burns_one_verify() -> None:
    """A user row with a NULL/empty password must fail via the dummy path, not short-circuit —
    otherwise it's distinguishable by timing from a real wrong-password attempt."""
    _reset_dummy()
    h = _CountingHasher()
    assert await verify_credentials(_User(""), "wrong", hasher=h) is False
    assert len(h.checks) == 1


async def test_dummy_digest_is_computed_once_and_reused() -> None:
    _reset_dummy()
    h = _CountingHasher()
    await verify_credentials(None, "a", hasher=h)
    await verify_credentials(None, "b", hasher=h)
    assert len(h.makes) == 1  # dummy made once, reused on the second unknown-user attempt
    assert len(h.checks) == 2  # but each attempt still runs its own verify

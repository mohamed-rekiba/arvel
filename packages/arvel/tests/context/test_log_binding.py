"""Epic 001 Story 2 — session-scoped log context binding."""

from __future__ import annotations

import types
from collections.abc import Awaitable, Callable, Iterator
from typing import TYPE_CHECKING, cast

import pytest
from arvel.context import Context, ContextRepository, bind_repository, reset_repository
from arvel.facades import Log
from arvel.testing.observability import FakeObservability

if TYPE_CHECKING:
    from arvel.auth.manager import AuthManager


@pytest.fixture
def fresh_context() -> Iterator[ContextRepository]:
    repo = ContextRepository()
    token = bind_repository(repo)
    try:
        yield repo
    finally:
        reset_repository(token)


def test_log_carries_request_user_and_tenant(fresh_context: ContextRepository) -> None:
    Context.add("request_id", "req-1")
    Context.add("user_id", "42")
    Context.add("tenant_id", "acme")

    with FakeObservability() as obs:
        Log.info("order.created")

    obs.assert_logged("order.created", request_id="req-1", user_id="42", tenant_id="acme")


def test_user_id_coerced_to_string(fresh_context: ContextRepository) -> None:
    Context.add("user_id", 7)

    with FakeObservability() as obs:
        Log.info("user.event")

    obs.assert_logged("user.event", user_id="7")


def test_no_context_no_none_keys(fresh_context: ContextRepository) -> None:
    with FakeObservability() as obs:
        Log.info("cli.command")

    records = [r for r in obs.log_records if r.body == "cli.command"]
    assert records, "expected the log record to be captured"
    attrs = records[0].attributes
    assert "user_id" not in attrs
    assert "tenant_id" not in attrs


def test_redaction_applies(
    fresh_context: ContextRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_REDACT_FIELDS", "password")

    with FakeObservability() as obs:
        Log.info("auth.attempt", password="hunter2")

    records = [r for r in obs.log_records if r.body == "auth.attempt"]
    assert records
    assert records[0].attributes["password"] == "[REDACTED]"


def test_explicit_context_wins_over_bound_context(fresh_context: ContextRepository) -> None:
    Context.add("user_id", "ambient")

    with FakeObservability() as obs:
        Log.info("explicit", user_id="passed-in")

    obs.assert_logged("explicit", user_id="passed-in")


async def test_optional_authenticate_binds_user_id(fresh_context: ContextRepository) -> None:
    from arvel.auth.middleware.authenticate import OptionalAuthenticate

    class _User:
        id = 99

    class _Manager:
        async def user(self, _request: object) -> _User:
            return _User()

    request = types.SimpleNamespace(state=types.SimpleNamespace())

    async def call_next(_request: object) -> str:
        return "ok"

    middleware = OptionalAuthenticate(manager=cast("AuthManager", _Manager()))
    handler: Callable[[object, Callable[[object], Awaitable[str]]], Awaitable[str]] = (
        middleware.handle
    )
    await handler(request, call_next)

    assert Context.get("user_id") == "99"

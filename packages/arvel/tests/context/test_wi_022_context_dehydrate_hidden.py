"""WI-arvel-022: hidden context survives the dehydrate -> hydrate round-trip.

Laravel's `Context` dehydrates both visible and hidden stores when a job is
queued, and hydrates both when the worker picks it up. "Hidden" means hidden
from logs and `all()`/`get()`, not from the queue — the docs' `dehydrating`
example adds hidden data precisely so it rides along.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from arvel.context import (
    Context,
    ContextRepository,
    bind_repository,
    reset_repository,
)
from arvel.context.repository import current_repository


@pytest.fixture(autouse=True)
def fresh_context() -> Iterator[ContextRepository]:
    repo = ContextRepository()
    token = bind_repository(repo)
    try:
        yield repo
    finally:
        reset_repository(token)


def test_dehydrate_payload_shape() -> None:
    Context.add("user_id", "7")
    Context.add_hidden("token", "s3cret")
    assert Context.dehydrate() == {
        "data": {"user_id": "7"},
        "hidden": {"token": "s3cret"},
    }


def test_hidden_round_trips_to_a_worker_repository() -> None:
    # Dispatcher side: build a payload with both stores.
    Context.add("request_id", "abc")
    Context.add_hidden("locale", "fr")
    payload = Context.dehydrate()

    # Worker side: a fresh repository hydrates the payload.
    worker = ContextRepository()
    worker.hydrate(payload)

    assert worker.get("request_id") == "abc"
    assert worker.get_hidden("locale") == "fr"
    # Hidden remains hidden from the visible view and logs surface.
    assert "locale" not in worker.all()
    assert worker.all_hidden() == {"locale": "fr"}


def test_empty_hidden_round_trips_cleanly() -> None:
    Context.add("only", "visible")
    payload = Context.dehydrate()
    assert payload["hidden"] == {}

    worker = ContextRepository()
    worker.hydrate(payload)
    assert worker.get("only") == "visible"
    assert worker.all_hidden() == {}


def test_dehydrate_snapshot_is_decoupled_from_live_store() -> None:
    Context.add("k", "v")
    Context.add_hidden("h", "x")
    payload = Context.dehydrate()

    # Mutating the live repository must not change an already-taken snapshot.
    current_repository().add("k", "changed")
    current_repository().forget_hidden("h")

    assert payload == {"data": {"k": "v"}, "hidden": {"h": "x"}}

"""Coverage — facade accessors, swap/fake, and error paths (doc 06)."""

from __future__ import annotations

import pytest

from arvel.support.facades import (
    DB,
    Auth,
    Cache,
    Config,
    Crypt,
    Event,
    Facade,
    Gate,
    Hash,
    Http,
    Lang,
    Log,
    Mail,
    Queue,
    Route,
    Storage,
    View,
    set_application,
)


def test_each_facade_accessor() -> None:
    expected = {
        Config: "config",
        Log: "log",
        Event: "events",
        Hash: "hash",
        Crypt: "encrypter",
        Http: "http",
        Route: "router",
        DB: "db",
        Lang: "translator",
        Cache: "cache",
        Storage: "filesystem",
        Mail: "mail",
        View: "view",
        Queue: "queue",
        Auth: "auth",
        Gate: "gate",
    }
    for facade, key in expected.items():
        assert facade.accessor() == key


def test_base_accessor_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        Facade.accessor()


def test_swap_and_clear() -> None:
    sentinel = object()
    Cache.swap(sentinel)
    assert Cache._resolve_root() is sentinel
    Facade.clear_swapped()
    set_application(None)  # reset roots


def test_fake_class_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        Config.fake()  # no fake_class defined

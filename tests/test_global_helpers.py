"""Coverage — the global helper shorthands (dd/dump, path helpers, transform,
per-request accessors, and the small pure utilities)."""

from __future__ import annotations

import enum

import pytest

from arvel.http.helpers import cookie, old, request, session  # http-layer (read the request)
from arvel.support.helpers import (
    base_path,
    class_basename,
    config_path,
    dd,
    dump,
    enum_value,
    lang_path,
    literal,
    noop,
    storage_path,
    transform,
    windows_os,
)


# --- debug -------------------------------------------------------------------
def test_dump_returns_its_argument(capsys: pytest.CaptureFixture[str]) -> None:
    assert dump(42) == 42  # single arg passes through
    assert dump(1, 2) == (1, 2)  # multiple -> tuple


def test_dd_raises_dumpdie_in_a_script_but_returns_in_a_repl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from arvel.support.helpers import DumpDie

    # non-interactive (a script / request) -> raise DumpDie, an *Exception* (not SystemExit, which
    # would slip past `except Exception` and escape to the ASGI server / kill the worker).
    monkeypatch.setattr("arvel.support.helpers._in_interactive_shell", lambda: False)
    assert not issubclass(DumpDie, SystemExit)  # the whole point: catchable by `except Exception`
    with pytest.raises(DumpDie):
        dd("x")
    # interactive shell -> dumps and returns, so it never kills the session
    monkeypatch.setattr("arvel.support.helpers._in_interactive_shell", lambda: True)
    assert dd("x") is None


# --- filesystem paths --------------------------------------------------------
def test_path_helpers_join_onto_the_base(monkeypatch: pytest.MonkeyPatch) -> None:
    # no bound application -> base is "."
    assert base_path() == "."
    assert base_path("a/b") == "./a/b"
    assert storage_path("logs") == "./storage/logs"
    # config/lang fall back to {base}/config, {base}/lang without an override
    assert config_path() == "./config"
    assert lang_path("en.json") == "./lang/en.json"


# --- transform ---------------------------------------------------------------
def test_transform_runs_only_when_filled() -> None:
    assert transform(5, lambda n: n * 2) == 10
    assert transform(None, lambda n: n * 2, default="fallback") == "fallback"
    assert transform("", lambda s: s.upper(), default=lambda: "def") == "def"  # blank -> default


# --- per-request accessors soft-fail off a request cycle ---------------------
def test_request_accessors_are_safe_outside_a_request() -> None:
    assert request() is None
    assert session() is None
    assert cookie("sid", "missing") == "missing"
    assert old() == {}
    assert old("field", "d") == "d"


# --- small pure utilities ----------------------------------------------------
def test_class_basename() -> None:
    assert class_basename({}) == "dict"  # instance -> its class name
    assert class_basename(dict) == "dict"  # accepts a class too


def test_enum_value() -> None:
    class Color(enum.Enum):
        RED = "red"

    assert enum_value(Color.RED) == "red"
    assert enum_value(7) == 7  # non-enum passes through


def test_literal_makes_an_ad_hoc_object() -> None:
    obj = literal(name="x", count=1)
    assert obj.name == "x"
    assert obj.count == 1


def test_noop_swallows_anything() -> None:
    assert noop() is None
    assert noop(1, 2, key="v") is None


def test_windows_os_is_a_bool() -> None:
    assert isinstance(windows_os(), bool)


def test_bcrypt_helper_uses_the_bcrypt_driver() -> None:
    # the helper is named `bcrypt`, so it must produce a bcrypt hash (not the Argon2id default)
    from arvel.security import Hasher
    from arvel.support.helpers import bcrypt

    digest = bcrypt("secret-value")
    assert digest.startswith(("$2a$", "$2b$", "$2y$"))  # bcrypt format, not $argon2
    assert Hasher(driver="bcrypt").check("secret-value", digest)

"""Config repository (dotted keys) + the config() helper + app() accessor."""

from __future__ import annotations

import pytest

from arvel.kernel import Container, Repository, app, config, env, has_application, set_application
from arvel.kernel.config import config_default


def test_env_reads_and_coerces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARVEL_TEST_VAR", "true")
    assert env("ARVEL_TEST_VAR") is True
    monkeypatch.setenv("ARVEL_TEST_VAR", "false")
    assert env("ARVEL_TEST_VAR") is False
    monkeypatch.setenv("ARVEL_TEST_VAR", "null")
    assert env("ARVEL_TEST_VAR") is None
    monkeypatch.setenv("ARVEL_TEST_VAR", "plain-string")
    assert env("ARVEL_TEST_VAR") == "plain-string"
    monkeypatch.delenv("ARVEL_TEST_VAR", raising=False)
    assert env("ARVEL_TEST_VAR", "fallback") == "fallback"


def test_get_dotted() -> None:
    repo = Repository({"app": {"name": "arvel", "debug": False}})
    assert repo.get("app.name") == "arvel"
    assert repo.get("app.debug") is False
    assert repo.get("app.missing", "fallback") == "fallback"
    assert repo.get("nope.deep", None) is None


def test_set_creates_nested() -> None:
    repo = Repository()
    repo.set("db.connections.pg.host", "localhost")
    assert repo.get("db.connections.pg.host") == "localhost"
    assert isinstance(repo.all()["db"], dict)


def test_has() -> None:
    repo = Repository({"a": {"b": None}})
    assert repo.has("a.b") is True  # present even though value is None
    assert repo.has("a.c") is False


def test_set_over_scalar_intermediate_clobbers_and_logs() -> None:
    from structlog.testing import capture_logs

    # turning a scalar into a section auto-vivifies (Laravel parity) but emits a debug log event.
    repo = Repository({"app": "a-string"})
    with capture_logs() as logs:
        repo.set("app.name", "x")
    assert repo.get("app.name") == "x"  # clobbered into a section
    assert any(log.get("event") == "config_set_replacing_scalar_with_section" for log in logs)


def test_all_returns_a_snapshot_not_live_state() -> None:
    # H2: mutating the result of all() must NOT leak back into the repository.
    repo = Repository({"app": {"name": "arvel", "nested": {"k": 1}}})
    snapshot = repo.all()
    snapshot["app"]["name"] = "hacked"  # type: ignore[index]
    snapshot["app"]["nested"]["k"] = 999  # type: ignore[index]
    assert repo.get("app.name") == "arvel"  # unchanged
    assert repo.get("app.nested.k") == 1  # nested also protected (deep copy)


def test_app_accessor_requires_bootstrap() -> None:
    set_application(None)
    assert has_application() is False
    with pytest.raises(RuntimeError):
        app()


def test_env_literal_variants_and_case_insensitivity(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = {
        "(true)": True,
        "(false)": False,
        "(null)": None,
        "empty": "",
        "(empty)": "",
        "TRUE": True,  # case-insensitive
        "Null": None,
    }
    for raw, expected in cases.items():
        monkeypatch.setenv("ARVEL_LIT", raw)
        result = env("ARVEL_LIT")
        assert result == expected and type(result) is type(expected)
    monkeypatch.setenv("ARVEL_LIT", "")  # an explicitly empty value is returned as ""
    assert env("ARVEL_LIT") == ""
    monkeypatch.delenv("ARVEL_LIT", raising=False)


def test_get_through_non_dict_intermediate_returns_default() -> None:
    repo = Repository({"app": {"name": "arvel"}})
    assert repo.get("app.name.sub", "d") == "d"  # name is a str, not a dict
    assert repo.get("", "d") == "d"  # empty key
    assert repo.get("app.", "d") == "d"  # trailing dot


def test_repr_redacts_values() -> None:
    repo = Repository({"db": {"password": "s3cret"}, "app": {"key": "tok"}})
    text = repr(repo)
    assert "s3cret" not in text and "tok" not in text
    assert "db" in text and "app" in text  # shape only


def test_config_default_without_app_returns_fallback() -> None:
    set_application(None)
    assert config_default("anything", "fallback") == "fallback"


def test_config_default_with_app_reads_then_falls_back() -> None:
    c = Container()
    c.instance("config", Repository({"auth": {"timeout": 900}}))
    set_application(c)
    try:
        assert config_default("auth.timeout", 60) == 900  # present → read
        assert config_default("auth.missing", 60) == 60  # absent → fallback
    finally:
        set_application(None)


def test_config_facade_proxies_and_swaps() -> None:
    from arvel.support.facades import Config

    Config.swap(Repository({"app": {"name": "facaded"}}))
    try:
        assert Config.get("app.name") == "facaded"
        assert Config.has("app.name") is True
    finally:
        Config.clear_swapped()


def test_config_helper_reads_from_container() -> None:
    c = Container()
    c.instance("config", Repository({"app": {"name": "myapp"}}))
    set_application(c)  # a Container satisfies the app accessor (.make)
    try:
        assert has_application() is True
        assert config("app.name") == "myapp"
        assert config("app.missing", "d") == "d"
        assert isinstance(config(), Repository)
        assert app("config").get("app.name") == "myapp"
    finally:
        set_application(None)

"""View-global parity (Laravel Blade helpers): templates can now call route()/url()/config()/asset()
(alongside the existing can/cannot/trans). They resolve through the bound app and degrade safely when no
app is present, so templates never crash. The app-resolved path is exercised end-to-end via the serve path."""

from __future__ import annotations

import pytest

from arvel.kernel.globals import set_application
from arvel.views import ViewFactory, _asset, _config, _route, _url


@pytest.fixture(autouse=True)
def _no_bootstrapped_app() -> object:
    """These tests assert the **no-app** degraded path, so guarantee a clean global app regardless of
    test order — a sibling tool/test (e.g. the facade-stub generator's _boot) can leak a bootstrapped
    app into the process. Reset before and after so the contract holds independent of ordering."""
    set_application(None)
    yield
    set_application(None)


def test_url_globals_registered() -> None:
    env = ViewFactory("resources/views").env
    for name in ("route", "url", "config", "asset", "can", "cannot", "trans", "trans_choice"):
        assert name in env.globals


def test_config_degrades_to_default_without_app() -> None:
    # no application bootstrapped in this unit context → returns the supplied default
    assert _config("app.name", "fallback") == "fallback"
    assert _config("missing.key") is None


def test_route_degrades_to_hash_without_app() -> None:
    assert _route("posts.show", id=1) == "#"


def test_url_joins_path() -> None:
    # no app.url configured → just the normalized path
    assert _url("/login") == "/login"
    assert _url("login") == "/login"
    assert _url() == "/"


def test_asset_joins_path() -> None:
    assert _asset("css/app.css") == "/css/app.css"
    assert _asset("/js/app.js") == "/js/app.js"

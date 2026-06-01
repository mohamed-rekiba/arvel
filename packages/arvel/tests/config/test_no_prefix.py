"""Annotated[str, NoPrefix] env opt-out."""

from __future__ import annotations

from typing import Annotated

import pytest


def test_no_prefix_marker_importable() -> None:
    from arvel.config import NoPrefix

    assert NoPrefix is not None


def test_no_prefix_field_reads_unprefixed_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from arvel.config import ArvelSettings, NoPrefix

    monkeypatch.setenv("SECRET_KEY", "shhh")
    monkeypatch.setenv("APP_NAME", "blog")

    class AppSettings(ArvelSettings):
        name: str = "default"
        secret_key: Annotated[str, NoPrefix] = ""

    s = AppSettings()
    assert s.name == "blog"  # uses derived prefix APP_
    assert s.secret_key == "shhh"  # bypasses prefix


def test_no_prefix_does_not_read_prefixed_value(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from arvel.config import ArvelSettings, NoPrefix

    monkeypatch.setenv("APP_SECRET_KEY", "wrong-source")
    # SECRET_KEY itself not set

    class AppSettings(ArvelSettings):
        secret_key: Annotated[str, NoPrefix] = "default"

    s = AppSettings()
    # NoPrefix means: read SECRET_KEY *only*, never APP_SECRET_KEY
    assert s.secret_key == "default"


def test_no_prefix_works_on_int_field(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from arvel.config import ArvelSettings, NoPrefix

    monkeypatch.setenv("PORT", "9090")

    class AppSettings(ArvelSettings):
        port: Annotated[int, NoPrefix] = 8080

    s = AppSettings()
    assert s.port == 9090

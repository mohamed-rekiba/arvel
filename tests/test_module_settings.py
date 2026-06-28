"""Per-module typed settings read their section from config() (DR-0016) — the rollout's read path."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.kernel import Application, set_application


def _app(**sections: Any) -> Application:
    app = Application()
    repo = app.make("config")
    for key, value in sections.items():
        repo.set(key, value)
    set_application(app)
    return app


def test_broadcasting_settings_reads_config() -> None:
    from arvel.broadcasting import BroadcastingSettings, BroadcastManager

    _app(broadcasting={"default": "pusher"})
    try:
        assert BroadcastingSettings().default == "pusher"
        assert BroadcastManager().default_driver() == "pusher"
    finally:
        set_application(None)


def test_search_settings_reads_config() -> None:
    from arvel.search import SearchManager, SearchSettings

    _app(search={"driver": "meilisearch"})
    try:
        assert SearchSettings().driver == "meilisearch"
        assert SearchManager().default_driver() == "meilisearch"
    finally:
        set_application(None)


def test_view_settings_reads_config() -> None:
    from arvel.views.provider import ViewSettings

    _app(view={"paths": "templates"})
    try:
        assert ViewSettings().paths == "templates"
    finally:
        set_application(None)
    _app(view={"paths": ["a", "b"]})  # multi-root is also valid (str | list[str])
    try:
        assert ViewSettings().paths == ["a", "b"]
    finally:
        set_application(None)


def test_filesystem_settings_default_and_defaults() -> None:
    from arvel.filesystem import FilesystemSettings

    _app(filesystems={"default": "s3"})
    try:
        assert FilesystemSettings().default == "s3"
    finally:
        set_application(None)
    set_application(None)
    assert FilesystemSettings().default == "local"  # no app → default


def test_settings_without_app_use_defaults() -> None:
    from arvel.broadcasting import BroadcastingSettings
    from arvel.search import SearchSettings

    set_application(None)
    assert BroadcastingSettings().default == "log"
    assert SearchSettings().driver == "array"


def test_invalid_view_paths_type_is_rejected() -> None:
    import msgspec

    from arvel.views.provider import ViewSettings

    _app(view={"paths": 123})  # an int is neither str nor list[str]
    try:
        with pytest.raises(msgspec.ValidationError):
            ViewSettings()
    finally:
        set_application(None)

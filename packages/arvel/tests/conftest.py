"""Shared pytest fixtures for the ``arvel`` package tests.

ORM fixtures (``engine`` / ``session_maker`` / ``session``) live in the
workspace-root ``conftest.py`` so every package's tests inherit them through
pytest's conftest hierarchy.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

# Make the Testcontainers emulator fixtures available to every test, regardless
# of subdirectory. Tests opt in by marking themselves @pytest.mark.requires_emulator
# and requesting the fixture by name; collection stays cheap because the fixtures
# only run when their tests are actually selected.
# Stays in this conftest (rather than the workspace root) because the dotted
# plugin path is resolved against ``packages/arvel/tests/`` on sys.path.
pytest_plugins = ["integration.emulators.fixtures"]

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def reset_global_state() -> Iterator[None]:
    """Tear down all process-level singletons after every test.

    Resets:
    - _lookup_registry._REGISTRY — dotted-key config modules
    - config/registry._REGISTERED — ArvelSettings subclasses
    - Router._instance — buffered route specs
    - Config._container — Pydantic config facade
    - os.environ — prevents .env loads from leaking across tests
    """
    env_snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(env_snapshot)

    from arvel.config._lookup_registry import reset as _reset_lookup
    from arvel.config.registry import clear as _clear_settings_reg
    from arvel.config.repository import Config
    from arvel.routing import Router

    _reset_lookup()
    _clear_settings_reg()
    Router.reset_singleton()
    Config._container = None  # pyright: ignore[reportPrivateUsage]

    from arvel.facades.event import Event as _EventFacade

    _EventFacade.dispatcher = None  # pyright: ignore[reportPrivateUsage]

    # Polymorphic morph map is process-global — clear it so registrations from one
    # test don't change another test's stored type tokens.
    from arvel.database.orm.morph_map import reset_morph_map

    reset_morph_map()


@pytest.fixture
def clean_env() -> Iterator[None]:
    """Snapshot/restore os.environ around a test."""
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


@pytest.fixture
def tmp_app_path(tmp_path: Path) -> Path:
    """A temp directory that can act as the application base_path."""
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "config").mkdir()
    return tmp_path

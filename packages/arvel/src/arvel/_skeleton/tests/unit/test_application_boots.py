"""Unit test: the application can be constructed without booting providers."""

from __future__ import annotations

from arvel import Application
from bootstrap.app import create_application


def test_create_application_returns_application() -> None:
    app = create_application()
    assert isinstance(app, Application)

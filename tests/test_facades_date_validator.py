"""F2 — Date and Validator facades (spec 06: Date->date, Validator->validator).

Both accessors are bound by discovered framework providers (DateServiceProvider,
ValidationServiceProvider) and the facades forward to them."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from arvel.dates import Date as DateClass
from arvel.kernel.application import Application
from arvel.kernel.discovery import bootstrap_providers, clear_cache
from arvel.kernel.globals import set_application
from arvel.support.facades import Date, Validator
from arvel.validation import Validator as ValidatorClass


@pytest.fixture
def booted_app() -> Iterator[Application]:
    clear_cache()
    app = Application.configure().create()
    bootstrap_providers(app)
    asyncio.run(app.boot())
    set_application(app)
    try:
        yield app
    finally:
        set_application(None)


def test_date_accessor_is_bound(booted_app: Application) -> None:
    assert booted_app.make("date") is DateClass


def test_date_facade_forwards_to_date_class(booted_app: Application) -> None:
    assert isinstance(Date.now(), DateClass)
    assert isinstance(Date.today(), DateClass)


def test_validator_accessor_is_bound(booted_app: Application) -> None:
    assert hasattr(booted_app.make("validator"), "make")


def test_validator_facade_make_builds_a_validator(booted_app: Application) -> None:
    v: Any = Validator.make({"email": "a@b.com"}, {"email": "required|email"})
    assert isinstance(v, ValidatorClass)
    assert v.passes() is True


def test_validator_facade_make_detects_failure(booted_app: Application) -> None:
    v: Any = Validator.make({"email": "not-an-email"}, {"email": "required|email"})
    assert v.fails() is True

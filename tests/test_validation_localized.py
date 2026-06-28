"""C6 — validation messages resolve through the bound translator for the current locale,
falling back to the built-in English defaults. Test-first."""

from __future__ import annotations

import pytest

from arvel.kernel import Application, set_application
from arvel.localization import Translator, current_locale
from arvel.validation import Validator


@pytest.fixture
def app_with_translator() -> object:
    trans = Translator(
        {
            "es": {"validation": {"required": "El campo {field} es obligatorio."}},
            "en": {"validation": {"required": "The {field} field is required."}},
        }
    )
    app = Application()
    app.instance("translator", trans)
    set_application(app)
    token = current_locale.set("en")
    try:
        yield None
    finally:
        current_locale.reset(token)
        set_application(None)


def test_message_uses_translator_for_current_locale(app_with_translator: object) -> None:
    current_locale.set("es")
    v = Validator({"name": ""}, {"name": "required"})
    assert v.fails()
    assert v.errors()["name"] == ["El campo name es obligatorio."]


def test_message_falls_back_to_default_when_key_missing(app_with_translator: object) -> None:
    current_locale.set("es")
    # 'email' has no validation.email translation → built-in default
    v = Validator({"email": "nope"}, {"email": "email"})
    assert v.fails()
    assert "valid email" in v.errors()["email"][0].lower()


def test_message_default_when_no_app_bound() -> None:
    # no application/translator → unchanged built-in behavior
    set_application(None)
    v = Validator({"name": ""}, {"name": "required"})
    assert v.fails()
    assert v.errors()["name"] == ["The name field is required."]

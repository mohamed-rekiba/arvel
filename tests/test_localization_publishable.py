"""The localization provider ships default lang files, loads the app's lang/ override, and registers
the defaults as publishable (vendor:publish --tag=lang)."""

from __future__ import annotations

import json
from pathlib import Path

from arvel.kernel import Application
from arvel.localization.provider import LocalizationServiceProvider


def _provider_for(base_path: Path) -> Application:
    app = Application(base_path=str(base_path))
    provider = LocalizationServiceProvider(app)
    provider.register()
    provider.boot()
    return app


def test_shipped_validation_json_matches_default_messages() -> None:
    """Guard against drift between validation's _DEFAULT_MESSAGES and the shipped lang file."""
    import arvel.localization
    from arvel.validation import _DEFAULT_MESSAGES

    lang_file = Path(arvel.localization.__file__).parent / "lang" / "en" / "validation.json"
    assert json.loads(lang_file.read_text()) == _DEFAULT_MESSAGES


def test_framework_validation_defaults_are_loaded(tmp_path: Path) -> None:
    app = _provider_for(tmp_path)  # no app lang/ → only the framework defaults
    translator = app.make("translator")
    assert (
        translator.get("validation.required", {"field": "email"}) == "The email field is required."
    )
    assert translator.get("auth.unverified") == "Your email address is not verified."
    assert translator.get("http.csrf") == "CSRF token mismatch"


def test_defaults_registered_publishable_under_lang_tag(tmp_path: Path) -> None:
    app = _provider_for(tmp_path)
    assert "lang" in app.published  # vendor:publish --tag=lang has something to copy
    dests = set(app.published["lang"].values())
    # must be the app's actual configured lang dir, not "lang" relative to the CLI's CWD
    assert dests == {str(tmp_path / "lang")}


def test_defaults_publish_into_with_lang_dir_override(tmp_path: Path) -> None:
    app = Application(base_path=str(tmp_path))
    app.lang_dir = str(tmp_path / "resources" / "lang")  # simulates with_lang_dir(...)
    provider = LocalizationServiceProvider(app)
    provider.register()
    dests = set(app.published["lang"].values())
    assert dests == {str(tmp_path / "resources" / "lang")}


def test_app_lang_overrides_framework_default(tmp_path: Path) -> None:
    lang = tmp_path / "lang" / "en"
    lang.mkdir(parents=True)
    (lang / "validation.json").write_text(json.dumps({"required": "PLEASE fill in {field}!"}))
    app = _provider_for(tmp_path)
    translator = app.make("translator")
    # app value wins…
    assert translator.get("validation.required", {"field": "email"}) == "PLEASE fill in email!"
    # …while un-overridden framework defaults still resolve
    assert (
        translator.get("validation.email", {"field": "x"}) == "The x must be a valid email address."
    )


def test_validation_uses_localized_message_end_to_end(tmp_path: Path) -> None:
    from arvel.kernel.globals import set_application
    from arvel.validation import ValidationException, Validator

    lang = tmp_path / "lang" / "en"
    lang.mkdir(parents=True)
    (lang / "validation.json").write_text(json.dumps({"required": "{field} is required, please."}))
    app = _provider_for(tmp_path)
    set_application(app)
    try:
        try:
            Validator({}, {"name": "required"}).validate()
            raise AssertionError("should have raised")
        except ValidationException as exc:
            assert exc.errors["name"][0] == "name is required, please."
    finally:
        set_application(None)

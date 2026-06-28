"""The generic HTTP status texts (the `abort(status)` / default-message fallbacks) are i18n-aware:
they route through trans("http.status.<code>") with the English dict as a safe fallback, so an app's
lang/<locale>/http.json can localize them — closing the last framework i18n gap (the _STATUS dict)."""

from __future__ import annotations

import json
from pathlib import Path

from arvel.http.exceptions import HttpException, _status_text
from arvel.kernel import Application
from arvel.kernel.globals import set_application
from arvel.localization import current_locale
from arvel.localization.provider import LocalizationServiceProvider


def _boot(base_path: Path) -> Application:
    """Boot a real app and make it global, so trans()/_status_text resolve through it (prod path)."""
    app = Application(base_path=str(base_path))
    provider = LocalizationServiceProvider(app)
    provider.register()
    provider.boot()
    set_application(app)
    return app


def test_status_text_defaults_to_english(tmp_path: Path) -> None:
    _boot(tmp_path)
    try:
        assert _status_text(404) == "Not Found"
        assert _status_text(419) == "Page Expired"
        assert _status_text(500) == "Server Error"
        assert _status_text(418) == "Server Error"  # unknown code → generic default, never a key
    finally:
        set_application(None)


def test_status_text_follows_active_locale(tmp_path: Path) -> None:
    lang = tmp_path / "lang" / "fr"
    lang.mkdir(parents=True)
    (lang / "http.json").write_text(json.dumps({"status": {"404": "Introuvable"}}))
    _boot(tmp_path)
    token = current_locale.set("fr")
    try:
        assert _status_text(404) == "Introuvable"  # app override wins
        assert _status_text(419) == "Page Expired"  # un-overridden → en fallback
    finally:
        current_locale.reset(token)
        set_application(None)


def test_abort_default_message_is_localized_but_explicit_wins(tmp_path: Path) -> None:
    lang = tmp_path / "lang" / "fr"
    lang.mkdir(parents=True)
    (lang / "http.json").write_text(json.dumps({"status": {"404": "Introuvable"}}))
    _boot(tmp_path)
    token = current_locale.set("fr")
    try:
        assert str(HttpException(404)) == "Introuvable"  # default text localized
        assert str(HttpException(404, "Gone fishing")) == "Gone fishing"  # explicit message wins
    finally:
        current_locale.reset(token)
        set_application(None)

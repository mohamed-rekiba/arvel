"""Framework user-facing messages route through trans(), backed by shipped, overridable lang groups."""

from __future__ import annotations

import json
from pathlib import Path

from arvel.kernel import Application
from arvel.localization import current_locale
from arvel.localization.provider import LocalizationServiceProvider


def _app(base_path: Path) -> Application:
    app = Application(base_path=str(base_path))
    provider = LocalizationServiceProvider(app)
    provider.register()
    provider.boot()
    return app


def test_auth_and_http_defaults_are_shipped(tmp_path: Path) -> None:
    app = _app(tmp_path)
    t = app.make("translator")
    # the framework lang groups load → real English text, not bare keys
    assert t.get("auth.unverified") == "Your email address is not verified."
    assert t.get("auth.already_authenticated") == "Already authenticated."
    assert t.get("auth.password_confirm") == "Password confirmation required."
    assert t.get("http.unauthorized") == "This action is unauthorized."
    assert t.get("http.csrf") == "CSRF token mismatch"
    assert t.get("http.too_many_requests") == "Too Many Requests"
    assert t.get("http.not_found") == "Not Found"


def test_app_can_override_a_framework_message(tmp_path: Path) -> None:
    lang = tmp_path / "lang" / "fr"
    lang.mkdir(parents=True)
    (lang / "auth.json").write_text(json.dumps({"unverified": "E-mail non vérifié."}))
    app = _app(tmp_path)
    t = app.make("translator")
    token = current_locale.set("fr")
    try:
        assert t.get("auth.unverified") == "E-mail non vérifié."  # app override wins
        assert t.get("http.csrf") == "CSRF token mismatch"  # un-overridden → en fallback
    finally:
        current_locale.reset(token)


def test_no_hardcoded_user_messages_remain_in_the_sources() -> None:
    """Guard: the routed strings must come from trans(), not literals (prevents regression)."""
    import arvel

    root = Path(arvel.__file__).parent
    for rel, needle in [
        ("auth/middleware.py", '"Your email address is not verified."'),
        ("auth/middleware.py", '"Already authenticated."'),
        ("auth/confirm.py", '"Password confirmation required."'),
        ("http/request.py", '"This action is unauthorized."'),
        ("http/middleware.py", '"CSRF token mismatch"'),
    ]:
        assert needle not in (root / rel).read_text(), f"{rel} still hardcodes {needle}"

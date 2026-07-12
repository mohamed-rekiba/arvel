"""C2 — typed settings: a typed VIEW over a config() section, auto-loaded on instantiation."""

from __future__ import annotations

import os

import msgspec
import pytest

from arvel.kernel import Application, AppSettings, Settings, config, load_dotenv, set_application


def test_app_settings_reads_and_validates_the_app_section() -> None:
    app = Application()
    app.make("config").set("app", {"name": "Acme", "env": "production", "debug": "true"})
    set_application(app)
    try:
        s = AppSettings()
        assert s.name == "Acme"
        assert s.env == "production"  # env stays str (open convention)
        assert s.debug is True  # coerced str → bool
        assert s.timezone == "UTC"  # default
    finally:
        set_application(None)


def test_app_settings_defaults_without_app() -> None:
    set_application(None)
    assert (AppSettings().name, AppSettings().env, AppSettings().debug) == ("arvel", "local", False)


class MailSettings(Settings):
    __config_key__ = "mail"
    host: str = "localhost"
    port: int = 25
    use_tls: bool = False


def _app_with(**sections: object) -> Application:
    app = Application()
    repo = app.make("config")
    for key, value in sections.items():
        repo.set(key, value)
    set_application(app)
    return app


def test_auto_loads_and_validates_its_config_section() -> None:
    # DR-0016: instantiating reads + validates config("mail"); config() is the single source.
    _app_with(mail={"port": "2525", "host": "smtp.example"})
    try:
        m = MailSettings()
        assert m.port == 2525  # coerced str → int from config("mail.port")
        assert m.host == "smtp.example"
        assert m.use_tls is False  # default (absent in config)
        assert config("mail.host") == m.host  # the typed view agrees with config()
    finally:
        set_application(None)


def test_explicit_kwargs_override_the_config_section() -> None:
    _app_with(mail={"port": "2525"})
    try:
        assert MailSettings(port=999).port == 999  # explicit wins over config
    finally:
        set_application(None)


def test_missing_section_falls_back_to_defaults() -> None:
    _app_with()  # no "mail" section
    try:
        assert (MailSettings().host, MailSettings().port) == ("localhost", 25)
    finally:
        set_application(None)


def test_without_an_app_uses_defaults_and_overrides() -> None:
    set_application(None)
    assert MailSettings().port == 25  # no app → no config read → defaults
    assert MailSettings(host="x").host == "x"  # explicit still applies


def test_invalid_value_raises() -> None:
    _app_with(mail={"port": "not-an-int"})
    try:
        with pytest.raises(msgspec.ValidationError):
            MailSettings()
    finally:
        set_application(None)


def test_missing_required_field_raises() -> None:
    class Required(Settings):
        __config_key__ = "req"
        token: str  # no default → required

    _app_with()  # section absent → required field missing
    try:
        with pytest.raises(msgspec.ValidationError):
            Required()
    finally:
        set_application(None)


def test_load_dotenv(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    env_file = Path(str(tmp_path)) / ".env"
    env_file.write_text('APP_NAME="from-dotenv"\n# comment\nAPP_DEBUG=true\n')
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_DEBUG", raising=False)
    load_dotenv(env_file)
    assert os.environ["APP_NAME"] == "from-dotenv"  # quotes stripped, comment line skipped
    assert os.environ["APP_DEBUG"] == "true"


def test_load_dotenv_handles_export_quotes_and_inline_comments(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the mature parser handles syntax the old hand-rolled one dropped or mangled.
    from pathlib import Path

    env_file = Path(str(tmp_path)) / ".env"
    env_file.write_text(
        "export APP_NAME='quoted value'   # inline comment\n"
        'APP_KEY="a#b=c"\n'  # '#' and '=' inside quotes are preserved
        "APP_WORKERS=8\n"
    )
    for var in ("APP_NAME", "APP_KEY", "APP_WORKERS"):
        monkeypatch.delenv(var, raising=False)
    load_dotenv(env_file)
    assert os.environ["APP_NAME"] == "quoted value"  # export stripped, inline comment dropped
    assert os.environ["APP_KEY"] == "a#b=c"  # quoted special chars intact
    assert os.environ["APP_WORKERS"] == "8"


def test_load_dotenv_does_not_override_real_env(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    env_file = Path(str(tmp_path)) / ".env"
    env_file.write_text("APP_NAME=from-file\n")
    monkeypatch.setenv("APP_NAME", "from-real-env")  # already present → must win
    load_dotenv(env_file)
    assert os.environ["APP_NAME"] == "from-real-env"


def test_load_dotenv_missing_file_is_noop(tmp_path: object) -> None:
    from pathlib import Path

    load_dotenv(Path(str(tmp_path)) / "does-not-exist.env")  # must not raise


def test_load_dotenv_kept_off_import_arvel() -> None:
    # The import must be lazy so `import arvel` stays light (the importtime NFR).
    import subprocess
    import sys

    code = "import arvel, sys; assert 'dotenv' not in sys.modules, 'dotenv loaded on import arvel'"
    subprocess.run([sys.executable, "-c", code], check=True)

"""ArvelSettings base class."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict


@pytest.fixture
def clean_env() -> Iterator[None]:
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


def test_arvel_settings_inherits_basesettings() -> None:
    from arvel.config import ArvelSettings
    from pydantic_settings import BaseSettings

    assert issubclass(ArvelSettings, BaseSettings)


def test_arvel_settings_reads_nested_env(clean_env: None) -> None:
    from arvel.config import ArvelSettings

    class DbConfig(ArvelSettings):
        host: str = "localhost"
        port: int = 5432

    os.environ["DB_HOST"] = "remote"
    os.environ["DB_PORT"] = "6543"
    cfg = DbConfig()
    assert cfg.host == "remote"
    assert cfg.port == 6543


def test_arvel_settings_ignores_extra_env(clean_env: None) -> None:
    from arvel.config import ArvelSettings

    class MailConfig(ArvelSettings):
        host: str = "smtp.example.com"

    os.environ["MAIL_HOST"] = "x"
    os.environ["MAIL_UNKNOWN"] = "should-not-error"
    cfg = MailConfig()
    assert cfg.host == "x"


def test_validation_error_wraps_into_config_error(clean_env: None) -> None:
    from arvel.config import ArvelSettings, ConfigError

    class StrictConfig(ArvelSettings):
        port: int = 5432

    os.environ["STRICT_PORT"] = "not-an-int"
    with pytest.raises(ConfigError) as excinfo:
        StrictConfig.from_environment()
    assert "port" in str(excinfo.value).lower()


def test_forbid_extra_subclass_with_match_prefix_ignores_unrelated_dotenv_entries(
    clean_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subclass that opts into ``dotenv_filtering="match_prefix"`` and uses
    ``extra="forbid"`` must not see ``.env`` entries that don't match its
    ``env_prefix``.

    Regression: pydantic-settings 2.x ``DotEnvSettingsSource`` returns every
    ``.env`` row regardless of ``env_prefix``. Combined with ``extra="forbid"``,
    a shared ``.env`` (e.g. ``APP_NAME=...``, ``DB_URL=...``) broke
    ``TaskiqQueueConfig`` import. The fix is per-subclass — applying
    ``match_prefix`` on the base would silently drop legitimate aliased fields
    (e.g. ``DB_URL`` reaching ``DbConfig.url``).
    """
    from arvel.config import ArvelSettings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "APP_NAME=MyApp\n"
        "APP_ENV=production\n"
        "DB_URL=sqlite+aiosqlite:///database/database.sqlite\n"
        "LOG_LEVEL=info\n"
    )

    class TaskiqLikeConfig(ArvelSettings):
        model_config = SettingsConfigDict(
            env_prefix="QUEUE_TASKIQ_",
            extra="forbid",
            dotenv_filtering="match_prefix",
        )

        broker_url: str = "redis://localhost:6379/0"

    cfg = TaskiqLikeConfig()
    assert cfg.broker_url == "redis://localhost:6379/0"


def test_match_prefix_still_resolves_prefixed_dotenv_entries(
    clean_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``match_prefix`` filters non-matching keys but keeps matching ones."""
    from arvel.config import ArvelSettings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "APP_NAME=MyApp\nQUEUE_TASKIQ_BROKER_URL=redis://prod:6379/2\n",
    )

    class TaskiqLikeConfig(ArvelSettings):
        model_config = SettingsConfigDict(
            env_prefix="QUEUE_TASKIQ_",
            extra="forbid",
            dotenv_filtering="match_prefix",
        )

        broker_url: str = "redis://localhost:6379/0"

    cfg = TaskiqLikeConfig()
    assert cfg.broker_url == "redis://prod:6379/2"


def test_base_settings_do_not_filter_dotenv_by_prefix(
    clean_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lock the narrower contract: the base ``ArvelSettings`` MUST NOT apply
    ``dotenv_filtering="match_prefix"``.

    Why this matters: ``DbConfig.url`` uses ``env_prefix="DB_"`` to read
    ``DB_URL``. If the base applied ``match_prefix``, the DotEnv source would
    drop unrelated keys before prefix resolution, silently breaking subclasses
    that rely on aliased env vars.
    """
    from arvel.config import ArvelSettings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "DB_URL=sqlite+aiosqlite:///database/database.sqlite\nDB_ECHO=true\n",
    )

    class _Probe(ArvelSettings):
        echo: bool = False

    # ``DB_ECHO`` is in the dotenv and matches the auto-derived ``PROBE_``
    # ... actually `_Probe` derives prefix `PROBE_`, so DB_ECHO doesn't match.
    # The real assertion: the BASE doesn't filter; loading shouldn't crash on
    # the dotenv even though no key matches the prefix.
    _Probe()  # No exception → base accepts mixed dotenv rows.

    # And the base's model_config must not declare ``dotenv_filtering``
    # this is a hard contract for subclasses with aliased flat env vars.
    assert "dotenv_filtering" not in ArvelSettings.model_config

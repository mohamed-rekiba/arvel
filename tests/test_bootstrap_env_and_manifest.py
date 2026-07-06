"""Bootstrap correctness: per-environment env files and base_path-anchored
package-manifest discovery (independent of process cwd)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from arvel.kernel.application import Application
from arvel.kernel.settings import load_environment


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in ("APP_ENV", "GREETING", "ONLY_BASE"):
        monkeypatch.delenv(key, raising=False)
    yield
    # load_environment writes to the real os.environ — scrub after each test too
    for key in ("APP_ENV", "GREETING", "ONLY_BASE"):
        os.environ.pop(key, None)


def _write(base: Path, name: str, body: str) -> None:
    (base / name).write_text(body)


# --- .env.[APP_ENV] precedence ---------------------------------------------
def test_env_specific_file_overrides_base_dotenv(
    tmp_path: Path, clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, ".env", "APP_ENV=testing\nGREETING=base\nONLY_BASE=yes\n")
    _write(tmp_path, ".env.testing", "GREETING=from-testing\n")
    load_environment(tmp_path)
    assert os.environ["GREETING"] == "from-testing"
    assert os.environ["ONLY_BASE"] == "yes"


def test_real_environment_beats_env_specific_file(
    tmp_path: Path, clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("GREETING", "real-env")
    _write(tmp_path, ".env", "GREETING=base\n")
    _write(tmp_path, ".env.testing", "GREETING=from-testing\n")
    load_environment(tmp_path)
    assert os.environ["GREETING"] == "real-env"


def test_app_env_from_real_environment_selects_file(
    tmp_path: Path, clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    _write(tmp_path, ".env", "GREETING=base\n")
    _write(tmp_path, ".env.staging", "GREETING=stage\n")
    load_environment(tmp_path)
    assert os.environ["GREETING"] == "stage"


def test_missing_env_specific_file_is_silent(
    tmp_path: Path, clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, ".env", "APP_ENV=testing\nGREETING=base\n")
    load_environment(tmp_path)
    assert os.environ["GREETING"] == "base"


# --- manifest anchored to base_path ------------------------------------------
def test_discover_reads_manifest_from_base_path_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import arvel.kernel.discovery as discovery

    base = tmp_path / "proj"
    (base / "bootstrap" / "cache").mkdir(parents=True)
    # a provider only the manifest knows about — an entry-point scan can't find it,
    # so resolving it proves the manifest was read (and from base_path, not cwd)
    (tmp_path / "fake_pkg_for_manifest.py").write_text(
        "class FakeManifestProvider:\n"
        "    def __init__(self, app):\n"
        "        self.app = app\n"
        "    def register(self):\n"
        "        pass\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    (base / "bootstrap" / "cache" / "packages.py").write_text(
        "PROVIDERS = ['fake_pkg_for_manifest:FakeManifestProvider']\n"
    )
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "bootstrap" / "cache").mkdir(parents=True)
    # decoy manifest at cwd — must be ignored in favor of the base_path one
    (elsewhere / "bootstrap" / "cache" / "packages.py").write_text("PROVIDERS = []\n")
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(discovery, "_cache", None)

    app = Application(base_path=str(base))
    providers = discovery.discover_providers(app)
    names = [p.__name__ for p in providers]
    assert "FakeManifestProvider" in names

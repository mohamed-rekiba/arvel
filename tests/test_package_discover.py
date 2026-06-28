"""Console/kernel (doc 13) — package:discover writes a persistent manifest the loader reads."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.kernel import discovery

runner = CliRunner()


def test_write_and_load_manifest(tmp_path: Path) -> None:
    path = discovery.write_manifest(str(tmp_path))
    assert path == tmp_path / "bootstrap" / "cache" / "packages.py"
    assert path.is_file()
    assert "PROVIDERS = [" in path.read_text()


def test_manifest_load_resolves_provider_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a manifest pointing at a real class resolves to that class
    cache = tmp_path / "bootstrap" / "cache"
    cache.mkdir(parents=True)
    (cache / "packages.py").write_text(
        "PROVIDERS = ['arvel.kernel.service_provider:ServiceProvider']\n"
    )
    monkeypatch.chdir(tmp_path)
    from arvel.kernel.service_provider import ServiceProvider

    loaded = discovery._load_manifest()
    assert loaded == [ServiceProvider]


def test_no_manifest_returns_none(tmp_path: Path) -> None:
    assert discovery._load_manifest(str(tmp_path)) is None


def test_discover_providers_reads_from_manifest_without_scanning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a manifest exists, ``discover_providers`` loads from it and skips the entry-point scan
    entirely (the cold-start fast path) — not just ``_load_manifest`` in isolation."""
    from arvel.kernel.application import Application
    from arvel.kernel.service_provider import ServiceProvider

    cache = tmp_path / "bootstrap" / "cache"
    cache.mkdir(parents=True)
    (cache / "packages.py").write_text(
        "PROVIDERS = ['arvel.kernel.service_provider:ServiceProvider']\n"
    )
    monkeypatch.chdir(tmp_path)
    discovery.clear_cache()

    def _must_not_scan(_dont: list[str]) -> list[type]:
        raise AssertionError("entry points were scanned despite a present manifest")

    monkeypatch.setattr(discovery, "_load_entry_points", _must_not_scan)
    try:
        providers = discovery.discover_providers(Application(), use_cache=True)
        assert ServiceProvider in providers  # came from the manifest, no scan
    finally:
        discovery.clear_cache()


def test_manifest_skips_stale_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stale manifest ref (package uninstalled/renamed) is warned + skipped, not fatal — the rest
    of the manifest still loads."""
    from arvel.kernel.service_provider import ServiceProvider

    cache = tmp_path / "bootstrap" / "cache"
    cache.mkdir(parents=True)
    (cache / "packages.py").write_text(
        "PROVIDERS = [\n"
        "    'arvel.kernel.service_provider:ServiceProvider',\n"
        "    'arvel.does_not_exist:Missing',\n"  # stale → warn + skip
        "]\n"
    )
    monkeypatch.chdir(tmp_path)
    assert discovery._load_manifest() == [ServiceProvider]  # good kept, stale dropped, no crash


def test_package_discover_command_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["package:discover"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "bootstrap" / "cache" / "packages.py").is_file()

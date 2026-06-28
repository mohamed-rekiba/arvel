"""B4 console polish (D5): the `extras` command no longer advertises the empty `settings` extra
(`arvel[settings]` adds nothing — it's msgspec-core, DR-0005). D4 (hidden-but-runnable alignment)
is a separate, larger pass (it needs per-command global-vs-project classification) — deferred."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


def test_extras_does_not_advertise_the_empty_settings_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["extras"])
    assert result.exit_code == 0
    assert "settings" not in result.output  # D5: empty extra is no longer advertised

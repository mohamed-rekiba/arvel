"""WI-017 / FR-017-004: arvel[all] extra is the union of all current extras."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

PYPROJECT = Path(__file__).resolve().parents[3] / "arvel" / "pyproject.toml"


def _load_extras() -> dict[str, list[str]]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return cast("dict[str, list[str]]", data["project"]["optional-dependencies"])


def test_all_extra_exists() -> None:
    extras = _load_extras()
    assert "all" in extras, "FR-017-004: arvel[all] extra must exist in pyproject.toml"


def test_all_extra_unions_every_other_extra() -> None:
    extras = _load_extras()
    other_extra_names = sorted(name for name in extras if name != "all")
    assert other_extra_names, "expected at least one non-'all' extra to exist"
    all_entry = extras["all"]
    msg = "FR-017-004: arvel[all] should reference itself via one combined entry"
    assert len(all_entry) == 1, msg
    entry = all_entry[0]
    for name in other_extra_names:
        matches = (
            f"[{name.split(',')[0]}" in entry
            or f",{name}" in entry
            or f"[{name}" in entry
            or name in entry
        )
        assert matches, f"FR-017-004: arvel[all] must include extra '{name}' (got: {entry!r})"

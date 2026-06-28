"""T1.7 — the lazy PEP-562 public surface of ``arvel`` (startup NFR / M1)."""

from __future__ import annotations

import subprocess
import sys

import pytest


def test_public_names_resolve_to_their_modules() -> None:
    import arvel
    import arvel.dates
    import arvel.kernel
    import arvel.support

    assert arvel.Application is arvel.kernel.Application
    assert arvel.Container is arvel.kernel.Container
    assert arvel.config is arvel.kernel.config
    assert arvel.Date is arvel.dates.Date
    assert arvel.now is arvel.dates.now
    assert arvel.Collection is arvel.support.Collection
    assert arvel.Str is arvel.support.Str


def test_unknown_attribute_raises() -> None:
    import arvel

    with pytest.raises(AttributeError):
        _ = arvel.Nonexistent  # type: ignore[attr-defined]


def test_dir_lists_public_surface() -> None:
    import arvel

    listed = dir(arvel)
    for name in ("Application", "Date", "Collection", "config", "now", "trans"):
        assert name in listed


def test_import_arvel_does_not_eagerly_load_capability_modules() -> None:
    # `import arvel` must not pull in kernel/dates/support/localization — only on access.
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import arvel, sys, json;"
            "print(json.dumps([m for m in ('arvel.kernel','arvel.dates','arvel.support',"
            "'arvel.localization') if m in sys.modules]))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    assert json.loads(out.stdout.strip()) == []


def test_attribute_access_triggers_lazy_import() -> None:
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import arvel, sys; _ = arvel.Date; print('arvel.dates' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "True"

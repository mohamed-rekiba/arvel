"""arvel.contracts — the public Protocol boundary is present, structural, and light."""

from __future__ import annotations

import subprocess
import sys
from typing import get_type_hints

import arvel.contracts as contracts

EXPECTED = {
    "Application",
    "Container",
    "ConfigRepository",
    "EventDispatcher",
    "ExceptionHandler",
    "Logger",
    "ServiceProvider",
    "Translator",
}


def test_all_foundation_protocols_exported() -> None:
    assert set(contracts.__all__) >= EXPECTED
    for name in EXPECTED:
        obj = getattr(contracts, name)
        assert getattr(obj, "_is_protocol", False), f"{name} must be a typing.Protocol"


def test_container_declares_resolution_surface() -> None:
    surface = {m for m in dir(contracts.Container) if not m.startswith("_")}
    assert {"bind", "singleton", "scoped", "make", "call", "instance", "tag", "tagged"} <= surface


def test_importing_contracts_pulls_no_heavy_libs() -> None:
    script = (
        "import arvel.contracts, sys, json;"
        "print(json.dumps([m for m in ('litestar','sqlalchemy','taskiq','PIL','pydantic','rich') "
        "if m in sys.modules]))"
    )
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    import json

    assert json.loads(out.stdout.strip()) == []


def test_protocols_have_resolvable_hints() -> None:
    # Forward refs ("Container", "Logger", …) must resolve against the module.
    for name in ("ConfigRepository", "Logger", "Application"):
        get_type_hints(getattr(contracts, name))

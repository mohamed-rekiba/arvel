"""Smoke checks for `benchmarks/bench_reverb.py` (FR-014-010/011, NFR-014-003/004).

These are signature + import checks. The actual benchmark runs live in
`benchmarks/bench_reverb.py` (entry point script) and the CI `bench-reverb`
job. We keep these as cheap unit tests so the benchmark surface can't
regress silently.
"""

from __future__ import annotations

import importlib.util
import inspect
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

_BENCH_PATH = Path(__file__).resolve().parents[4] / "benchmarks" / "bench_reverb.py"


def _load_bench_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bench_reverb", _BENCH_PATH)
    if spec is None or spec.loader is None:
        msg = f"failed to load bench module from {_BENCH_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not _BENCH_PATH.exists(), reason="bench_reverb.py not yet implemented")
def test_bench_publish_p99_latency_signature() -> None:
    """FR-014-010 — bench_publish_p99_latency(iterations: int) -> list[float] exists."""
    module = _load_bench_module()
    fn = getattr(module, "bench_publish_p99_latency", None)
    assert callable(fn), "bench_publish_p99_latency must be defined"
    sig = inspect.signature(cast("Callable[..., Any]", fn))
    assert "iterations" in sig.parameters, "iterations parameter required"


@pytest.mark.skipif(not _BENCH_PATH.exists(), reason="bench_reverb.py not yet implemented")
def test_bench_resident_memory_signature() -> None:
    """FR-014-010 — bench_resident_memory(connections: int, channels: int) -> int exists."""
    module = _load_bench_module()
    fn = getattr(module, "bench_resident_memory", None)
    assert callable(fn), "bench_resident_memory must be defined"
    sig = inspect.signature(cast("Callable[..., Any]", fn))
    assert "connections" in sig.parameters
    assert "channels" in sig.parameters


@pytest.mark.skipif(not _BENCH_PATH.exists(), reason="bench_reverb.py not yet implemented")
def test_bench_main_exists() -> None:
    """FR-014-010 — main() entry point returns int (exit code)."""
    module = _load_bench_module()
    fn = getattr(module, "main", None)
    assert callable(fn), "main() must be defined as the script entry"

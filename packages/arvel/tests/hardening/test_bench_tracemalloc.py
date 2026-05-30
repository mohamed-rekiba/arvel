"""WI-017 / FR-017-010: byte-granular memory bench via tracemalloc."""

from __future__ import annotations

import importlib
import inspect


def test_tracemalloc_function_exists() -> None:
    """FR-017-010: bench_reverb must expose bench_resident_memory_tracemalloc."""
    module = importlib.import_module("benchmarks.bench_reverb")
    fn = getattr(module, "bench_resident_memory_tracemalloc", None)
    assert callable(fn), (
        "FR-017-010: benchmarks/bench_reverb.py must define bench_resident_memory_tracemalloc()"
    )


def test_legacy_resident_memory_bench_still_exists() -> None:
    """FB-014-002 explicitly says keep bench_resident_memory() for back-compat."""
    module = importlib.import_module("benchmarks.bench_reverb")
    assert callable(getattr(module, "bench_resident_memory", None)), (
        "bench_resident_memory() must remain alongside the tracemalloc version"
    )


def test_tracemalloc_bench_uses_tracemalloc() -> None:
    """The new function must actually call tracemalloc, not just be a stub."""
    module = importlib.import_module("benchmarks.bench_reverb")
    fn = module.bench_resident_memory_tracemalloc
    source = inspect.getsource(fn)
    assert "tracemalloc" in source, (
        "FR-017-010: bench_resident_memory_tracemalloc() must use the tracemalloc module"
    )

"""Bench reverb calibration script and gate documentation."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CALIBRATION_SCRIPT = REPO_ROOT / "benchmarks" / "scripts" / "calibrate_bench_reverb.py"


def test_calibration_script_exists() -> None:
    """The re-runnable calibration helper must exist."""
    assert CALIBRATION_SCRIPT.exists(), (
        f"missing calibration helper: {CALIBRATION_SCRIPT.relative_to(REPO_ROOT)}"
    )


def test_calibration_script_is_runnable() -> None:
    """The script must define a main() and accept --runs."""
    text = CALIBRATION_SCRIPT.read_text(encoding="utf-8")
    assert "def main(" in text, "calibration script must define main()"
    assert "--runs" in text, "calibration script must accept --runs CLI flag"

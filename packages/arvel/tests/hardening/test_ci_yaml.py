"""CI workflow shape assertions.

bench-reverb must be a hard gate, bench-tracemalloc job must exist,
and sast/sca jobs must invoke bandit and pip-audit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

CI_YAML = Path(__file__).resolve().parents[4] / ".github" / "workflows" / "ci.yml"


def _ci() -> dict[str, dict[str, Any]]:
    if not CI_YAML.exists():
        raise FileNotFoundError(f".github/workflows/ci.yml not found at {CI_YAML}")
    raw = yaml.safe_load(CI_YAML.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "jobs" in raw:
        return cast("dict[str, dict[str, Any]]", raw["jobs"])
    return {}


def _all_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return list(job.get("steps", []))


def test_ci_yaml_exists() -> None:
    assert CI_YAML.exists(), f"CI workflow file missing at {CI_YAML}"


def test_bench_reverb_is_hard_gate() -> None:
    """bench-reverb must not be advisory (no continue-on-error)."""
    jobs = _ci()
    assert "bench-reverb" in jobs, "bench-reverb job must exist in ci.yml"
    job = jobs["bench-reverb"]
    if isinstance(job.get("continue-on-error"), bool):
        assert job["continue-on-error"] is False, (
            "FR-017-007: bench-reverb job must NOT have continue-on-error: true"
        )
    for step in _all_steps(job):
        assert step.get("continue-on-error") is not True, (
            f"FR-017-007: step {step.get('name')!r} in bench-reverb must NOT be advisory"
        )


def test_bench_tracemalloc_job_exists() -> None:
    """a bench-tracemalloc CI job must exist."""
    jobs = _ci()
    assert "bench-tracemalloc" in jobs, "FR-017-011: ci.yml must define a 'bench-tracemalloc' job"
    job = jobs["bench-tracemalloc"]
    assert job.get("continue-on-error") is not True, (
        "FR-017-011: bench-tracemalloc must be a hard gate"
    )


def test_sast_job_exists() -> None:
    """a 'sast' job running bandit must exist."""
    jobs = _ci()
    assert "sast" in jobs, "FR-017-013: ci.yml must define a 'sast' job"
    job = jobs["sast"]
    has_bandit = any("bandit" in (s.get("run", "") + s.get("name", "")) for s in _all_steps(job))
    assert has_bandit, "FR-017-013: 'sast' job must invoke bandit"


def test_sca_job_exists() -> None:
    """a 'sca' job running pip-audit must exist."""
    jobs = _ci()
    assert "sca" in jobs, "FR-017-014: ci.yml must define a 'sca' job"
    job = jobs["sca"]
    has_pip_audit = any(
        "pip-audit" in (s.get("run", "") + s.get("name", "")) for s in _all_steps(job)
    )
    assert has_pip_audit, "FR-017-014: 'sca' job must invoke pip-audit"

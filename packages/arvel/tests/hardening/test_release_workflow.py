"""Release workflow stub exists and fails closed."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

WORKFLOWS = Path(__file__).resolve().parents[4] / ".github" / "workflows"
RELEASE_YML = WORKFLOWS / "release-please.yml"
# release-please.yml opens release PRs on push to main; when a release PR
# merges, release-please pushes a `<package>-v<version>` tag. publish.yml is
# the workflow that triggers on those tags, runs `twine check`, and publishes.
PUBLISH_YML = WORKFLOWS / "publish.yml"


def _load_workflow(path: Path) -> dict[object, object]:
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), f"{path} must be a YAML mapping"
    return cast("dict[object, object]", raw)


def _as_dict(value: object) -> dict[object, object]:
    if isinstance(value, dict):
        return cast("dict[object, object]", value)
    return {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast("list[object]", value)
    return []


def test_release_workflow_exists() -> None:
    assert RELEASE_YML.exists(), f"missing release workflow: {RELEASE_YML}"
    assert PUBLISH_YML.exists(), f"missing publish workflow: {PUBLISH_YML}"


def test_release_workflow_triggers_on_version_tag() -> None:
    workflow = _load_workflow(PUBLISH_YML)
    # PyYAML parses a bare ``on:`` key as the Python bool True.
    on = _as_dict(workflow.get(True, workflow.get("on", {})))
    push = _as_dict(on.get("push", {}))
    tags = _as_list(push.get("tags", []))
    assert any("v" in str(t) for t in tags), (
        "publish workflow must trigger on push to <package>-v*.*.* tags"
    )


def test_release_workflow_fails_closed() -> None:
    """publish workflow must NOT execute twine upload.

    Scope check: only counts uncommented, executable shell lines (lines that
    start a `run:` block or are inside one). Documentation comments referring
    to 'twine upload' as a manual step are fine.
    """
    raw = PUBLISH_YML.read_text(encoding="utf-8")
    workflow = _load_workflow(PUBLISH_YML)
    jobs = _as_dict(workflow.get("jobs", {}))

    for job_name, job_value in jobs.items():
        job = _as_dict(job_value)
        for step_value in _as_list(job.get("steps", [])):
            step = _as_dict(step_value)
            run = step.get("run", "")
            if not isinstance(run, str):
                continue
            for line in run.splitlines():
                # strip shell comments and surrounding whitespace
                code = line.split("#", 1)[0].strip()
                if not code:
                    continue
                # ``echo "twine upload ..."`` only prints instructions; the
                # shell doesn't execute the printed text. That's fine.
                if code.startswith(("echo ", 'echo "', "echo '")):
                    continue
                assert "twine upload" not in code, (
                    f"{job_name}.{step.get('name', '?')} must not execute 'twine upload': {code!r}"
                )

    assert "twine check" in raw, "publish.yml must run 'twine check' as a dry-run validation"

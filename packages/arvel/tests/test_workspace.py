"""FR-001-001: monorepo workspace shape.

Sanity checks on workspace layout. These should pass as soon as the workspace is set
up (Step 1 of Stage 3b). Until then, they should fail.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_root_pyproject_declares_workspace_members() -> None:
    root_toml = REPO_ROOT / "pyproject.toml"
    assert root_toml.exists(), "Workspace root pyproject.toml missing"
    data = tomllib.loads(root_toml.read_text())
    workspace = data.get("tool", {}).get("uv", {}).get("workspace", {})
    members = workspace.get("members", [])
    assert "packages/*" in members or "packages/arvel" in members, (
        "tool.uv.workspace.members should include packages/*"
    )


@pytest.mark.parametrize("pkg", ["arvel"])
def test_each_workspace_member_has_pyproject(pkg: str) -> None:
    p = REPO_ROOT / "packages" / pkg / "pyproject.toml"
    assert p.exists(), f"Missing pyproject.toml for {pkg}"
    data = tomllib.loads(p.read_text())
    assert data["project"]["name"] == pkg
    assert data["project"]["requires-python"].startswith(">=3.14")


def test_arvel_imports() -> None:
    import arvel

    assert arvel.__version__ is not None

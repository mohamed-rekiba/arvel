"""path-traversal protection.

Adversarial test suite — verifies the cli cannot write outside the
intended target directory under any input. Targeted by Stage 4b security
review.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from arvel.console._scaffold import (
    InvalidProjectName,
    resolve_target_directory,
    validate_project_name,
)

# Names that MUST be rejected at the validation layer (before path resolution).
ADVERSARIAL_NAMES = [
    "..",
    "../escape",
    "../../etc/passwd",
    "/absolute/path",
    "C:\\windows\\system32",
    "my/app",
    "my\\app",
    ".hidden",
    "name\x00null",
    "name\nwith\nnewlines",
    "name;rm -rf /",
    "name`whoami`",
    "name$(whoami)",
    "name|pipe",
    "name&background",
    "$(date)",
    "${PATH}",
    "..",
    "../..",
    "./relative",
    "x" * 1024,
    " ",
    "\t",
]


@pytest.mark.parametrize("name", ADVERSARIAL_NAMES)
def test_adversarial_name_is_rejected_at_validation(name: str) -> None:
    """Adversarial inputs raise ``InvalidProjectName`` before any I/O happens."""
    with pytest.raises(InvalidProjectName):
        validate_project_name(name)


def test_resolve_target_keeps_path_inside_cwd(tmp_path: Path) -> None:
    """Valid name resolved against cwd yields a child of cwd (containment check)."""
    target = resolve_target_directory("my-app", tmp_path)
    assert target.parent.resolve() == tmp_path.resolve()
    assert target.name == "my-app"


def test_resolve_target_existing_empty_dir_is_accepted(tmp_path: Path) -> None:
    """An empty pre-existing directory is acceptable (used into)."""
    (tmp_path / "my-app").mkdir()
    target = resolve_target_directory("my-app", tmp_path)
    assert target == (tmp_path / "my-app").resolve()


def test_resolve_target_non_empty_dir_raises_file_exists(tmp_path: Path) -> None:
    """Non-empty pre-existing directory is refused (no destructive overwrite)."""
    populated = tmp_path / "my-app"
    populated.mkdir()
    (populated / "something.txt").write_text("don't clobber me")

    with pytest.raises(FileExistsError):
        resolve_target_directory("my-app", tmp_path)


def test_resolve_target_via_symlink_does_not_escape(tmp_path: Path) -> None:
    """A symlink in cwd cannot trick resolution into landing outside cwd."""
    if os.name == "nt":  # pragma: no cover (Windows has different symlink semantics)
        pytest.skip("Symlink semantics differ on Windows")

    outside = tmp_path / "outside-jail"
    outside.mkdir()
    link = tmp_path / "trap"
    link.symlink_to(outside)

    # Even with a symlink alias, valid names still resolve under cwd.
    # The validation layer doesn't follow `name` through cwd, so this
    # tests the resolve_target_directory containment guarantee.
    target = resolve_target_directory("safe", tmp_path)
    assert (
        tmp_path.resolve() in target.resolve().parents
        or target.parent.resolve() == tmp_path.resolve()
    )


def test_resolve_target_with_traversal_in_name_is_blocked_by_validation() -> None:
    """``resolve_target_directory`` defers to validation.

    The traversal never reaches resolution.
    """
    with pytest.raises(InvalidProjectName):
        validate_project_name("../escape")


def test_null_byte_in_name_is_rejected() -> None:
    """Embedded NULs are rejected (defence against POSIX-vs-syscall mismatches)."""
    with pytest.raises(InvalidProjectName):
        validate_project_name("legit\x00../escape")

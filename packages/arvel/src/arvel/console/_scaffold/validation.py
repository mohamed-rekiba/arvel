"""Project-name validation + target-directory resolution.

First line of defence against path-traversal attacks (NFR-004-003,
ADR-018 §Conventions, ADR-020 § Project name validation). Contract surface
only — bodies raise ``NotImplementedError`` until Stage 3b makes the
QA-Pre tests green.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

PROJECT_NAME_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]*$")
"""Allowlist regex for project names.

Lowercase letter to start, then lowercase letters, digits, underscores, or
hyphens. No path separators, no parent references, no dots, no spaces, no
uppercase. Anchored on both ends.
"""

MAX_PROJECT_NAME_LENGTH: Final[int] = 64
"""Maximum allowed project name length (defence against pathological input)."""


class InvalidProjectName(ValueError):  # noqa: N818 — public API name pre-dates linter rule
    """Raised when a project name fails the regex or length check.

    The message names the violated constraint so the CLI can pass it
    straight to stderr.
    """


def validate_project_name(name: str) -> str:
    """Return ``name`` unchanged if it satisfies the project-name allowlist.

    Validates in order:
    1. Length: ``1 <= len(name) <= MAX_PROJECT_NAME_LENGTH``.
    2. Regex: ``PROJECT_NAME_REGEX.fullmatch(name)`` is non-None.

    Raises ``InvalidProjectName`` with a message naming the violation.
    """
    if not isinstance(name, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        # Runtime defense-in-depth for un-typed callers; statically unreachable
        # when callers honour the `name: str` annotation, so mypy needs the
        # matching opt-out alongside the pyright one above.
        msg = f"project name must be a string, got {type(name).__name__}"  # type: ignore[unreachable]
        raise InvalidProjectName(msg)
    if len(name) == 0:
        raise InvalidProjectName("project name is empty")
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        msg = (
            f"project name exceeds max length of {MAX_PROJECT_NAME_LENGTH} "
            f"characters (got {len(name)})"
        )
        raise InvalidProjectName(msg)
    if PROJECT_NAME_REGEX.fullmatch(name) is None:
        msg = (
            f"project name {name!r} is invalid: must match "
            f"{PROJECT_NAME_REGEX.pattern} (lowercase letter start, then "
            f"lowercase letters, digits, underscores, or hyphens)"
        )
        raise InvalidProjectName(msg)
    return name


def resolve_target_directory(name: str, cwd: Path) -> Path:
    """Resolve ``cwd / name`` and assert it is safe to write to.

    The resolved path's parent MUST equal ``cwd.resolve()`` (containment
    check — prevents traversal even when the OS allows it). The target
    MUST either not exist, or exist and be empty.

    Returns the resolved target path.

    Raises:
    - ``InvalidProjectName`` if the containment check fails.
    - ``FileExistsError`` if the target exists and is non-empty.
    """
    validate_project_name(name)
    cwd_resolved = cwd.resolve()
    target = (cwd_resolved / name).resolve()
    # Containment check — belt-and-braces alongside the regex.
    if target.parent != cwd_resolved:
        msg = (
            f"resolved target {target} escapes cwd {cwd_resolved} — "
            f"refusing to write outside the working directory"
        )
        raise InvalidProjectName(msg)
    if target.exists():
        if not target.is_dir():
            msg = f"target {target} exists and is not a directory"
            raise FileExistsError(msg)
        # Empty dir is fine (used into); non-empty is refused.
        if any(target.iterdir()):
            msg = f"target directory {target} is not empty — refusing to overwrite"
            raise FileExistsError(msg)
    return target

"""Re-exec the global ``arvel`` launcher onto the project's ``.venv`` interpreter.

A globally-installed ``arvel`` (pipx, ``uv tool install``, system pip) runs on
the interpreter it was installed into — whose ``sys.path`` points at global
site-packages, not the project's ``.venv``. So importing the user's
``bootstrap/app.py`` would resolve the wrong arvel version and miss the
project's extras (asyncpg, argon2 wheels are ABI-specific per interpreter).

The fix: before doing anything, hand off via ``os.execve`` to the venv's own
``arvel`` (or ``python -m arvel``). From there everything runs exactly as if the
venv were activated — project-pinned version, project deps, the lot.

Opt out with ``ARVEL_NO_REEXEC=1``. The internal ``ARVEL_VENV_REEXEC=1`` flag is
the loop guard: it's set on the env we exec into, so the second leg never tries
to re-exec again.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from pathlib import Path

from arvel.console.bootstrap import find_project_root

_OPT_OUT = "ARVEL_NO_REEXEC"
_LOOP_GUARD = "ARVEL_VENV_REEXEC"
_VENV_DIRNAME = ".venv"


def _venv_python(root: Path) -> Path | None:
    if os.name == "nt":
        cand = root / _VENV_DIRNAME / "Scripts" / "python.exe"
    else:
        cand = root / _VENV_DIRNAME / "bin" / "python"
    return cand if cand.is_file() else None


def _venv_arvel(root: Path) -> Path | None:
    if os.name == "nt":
        cand = root / _VENV_DIRNAME / "Scripts" / "arvel.exe"
    else:
        cand = root / _VENV_DIRNAME / "bin" / "arvel"
    return cand if cand.is_file() else None


def _venv_has_arvel_package(venv_python: Path) -> bool:
    """True when an importable ``arvel`` lives under the venv's site-packages.

    Globs the venv's ``lib`` tree so we don't spawn the interpreter just to ask.
    Used only as the fallback signal when the ``arvel`` console script is absent.
    """
    venv_root = venv_python.parent.parent
    patterns = ("lib/python*/site-packages/arvel", "Lib/site-packages/arvel")
    return any(any(venv_root.glob(pattern)) for pattern in patterns)


def _already_inside(venv_python: Path) -> bool:
    """True when the running interpreter already belongs to this project's venv.

    Compares ``sys.prefix`` (the active environment root) to the project's
    ``.venv`` — NOT the interpreter binary. uv venvs symlink a single shared base
    CPython, so a globally-installed ``arvel`` and the project's ``.venv/bin/python``
    both resolve to the *same* ``python3`` file. An executable-path check would
    then wrongly report "already inside" and skip the re-exec, leaving commands
    running against the global site-packages instead of the project's deps.
    """
    venv_dir = venv_python.parent.parent
    try:
        return Path(sys.prefix).resolve() == venv_dir.resolve()
    except OSError:
        return False


def exec_into(target: str, args: list[str], env: dict[str, str]) -> None:
    """Replace this process with ``target``. On Windows, fall back to a child.

    ``os.execve`` on Windows spawns a child and the parent keeps running with a
    bogus PID, so we run a real subprocess and exit with its code instead.
    """
    # target is the project's own .venv interpreter/script path we located on
    # disk — no shell, no untrusted input. Re-exec is the whole point here.
    if os.name == "nt":
        result = subprocess.run([target, *args[1:]], env=env, check=False)  # noqa: S603 # nosec B603
        sys.exit(result.returncode)
    os.execve(target, args, env)  # noqa: S606 # nosec B606


def maybe_reexec_into_project_venv(argv: list[str]) -> None:
    """Re-exec onto the project's ``.venv`` interpreter when needed.

    Returns (does nothing) when already inside the venv, opted out, outside a
    project, when no ``.venv`` exists, or when the venv has no arvel to run.
    Otherwise this never returns — the process image is replaced.
    """
    if os.environ.get(_OPT_OUT) or os.environ.get(_LOOP_GUARD):
        return

    root = find_project_root()
    if root is None:
        return

    venv_python = _venv_python(root)
    if venv_python is None or _already_inside(venv_python):
        return

    env = {**os.environ, _LOOP_GUARD: "1"}

    venv_arvel = _venv_arvel(root)
    if venv_arvel is not None:
        target = str(venv_arvel)
        exec_into(target, [target, *argv[1:]], env)
        return

    if _venv_has_arvel_package(venv_python):
        target = str(venv_python)
        exec_into(target, [target, "-m", "arvel", *argv[1:]], env)
        return

    # .venv exists but has no arvel — let the normal flow surface its own error
    # rather than re-exec'ing into an interpreter that can't run us.


__all__ = ["maybe_reexec_into_project_venv"]

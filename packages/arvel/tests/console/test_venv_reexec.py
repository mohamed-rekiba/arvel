"""The global ``arvel`` re-execs onto the project's ``.venv`` interpreter.

A globally-installed launcher must hand off to ``<root>/.venv`` so commands run
the project-pinned arvel + its deps. These tests pin the precedence: opt-outs,
loop guard, already-inside, no-venv, outside-project, and the Windows branch.
``os.execve`` is patched everywhere so the test process is never replaced.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from arvel.console import _venv
from arvel.console._venv import maybe_reexec_into_project_venv


def _make_project(tmp_path: Path, *, with_arvel_script: bool = True) -> Path:
    """Lay out a fake project with bootstrap/app.py and a POSIX-style .venv."""
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("def create_application(): ...\n")
    bindir = tmp_path / ".venv" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "python").write_text("#!/usr/bin/env python\n")
    if with_arvel_script:
        (bindir / "arvel").write_text("#!/usr/bin/env python\n")
    return tmp_path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARVEL_NO_REEXEC", raising=False)
    monkeypatch.delenv("ARVEL_VENV_REEXEC", raising=False)
    # Default to POSIX behaviour; Windows test overrides this.
    monkeypatch.setattr(os, "name", "posix")


class TestReexecTriggers:
    def test_execs_into_venv_arvel_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_project(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.setattr(_venv.sys, "executable", "/usr/bin/python3")

        with patch.object(_venv.os, "execve") as execve:
            maybe_reexec_into_project_venv(["arvel", "migrate", "--seed"])

        execve.assert_called_once()
        target, args, env = execve.call_args.args
        assert target == str(root / ".venv" / "bin" / "arvel")
        assert args == [str(root / ".venv" / "bin" / "arvel"), "migrate", "--seed"]
        assert env["ARVEL_VENV_REEXEC"] == "1"

    def test_falls_back_to_python_dash_m_when_no_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_project(tmp_path, with_arvel_script=False)
        monkeypatch.chdir(root)
        monkeypatch.setattr(_venv.sys, "executable", "/usr/bin/python3")

        # No arvel script, but the package is importable in the venv.
        def _has_pkg(_p: object) -> bool:
            return True

        monkeypatch.setattr(_venv, "_venv_has_arvel_package", _has_pkg)

        with patch.object(_venv.os, "execve") as execve:
            maybe_reexec_into_project_venv(["arvel", "route:list"])

        target, args, _env = execve.call_args.args
        assert target == str(root / ".venv" / "bin" / "python")
        assert args == [target, "-m", "arvel", "route:list"]

    def test_no_reexec_when_venv_has_no_arvel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_project(tmp_path, with_arvel_script=False)
        monkeypatch.chdir(root)
        monkeypatch.setattr(_venv.sys, "executable", "/usr/bin/python3")

        def _no_pkg(_p: object) -> bool:
            return False

        monkeypatch.setattr(_venv, "_venv_has_arvel_package", _no_pkg)

        with patch.object(_venv.os, "execve") as execve:
            maybe_reexec_into_project_venv(["arvel", "migrate"])

        execve.assert_not_called()


class TestReexecSkips:
    def test_opt_out_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_project(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.setenv("ARVEL_NO_REEXEC", "1")
        monkeypatch.setattr(_venv.sys, "executable", "/usr/bin/python3")

        with patch.object(_venv.os, "execve") as execve:
            maybe_reexec_into_project_venv(["arvel", "migrate"])

        execve.assert_not_called()

    def test_loop_guard_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_project(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.setenv("ARVEL_VENV_REEXEC", "1")
        monkeypatch.setattr(_venv.sys, "executable", "/usr/bin/python3")

        with patch.object(_venv.os, "execve") as execve:
            maybe_reexec_into_project_venv(["arvel", "migrate"])

        execve.assert_not_called()

    def test_already_inside_venv(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_project(tmp_path)
        monkeypatch.chdir(root)
        venv_python = str(root / ".venv" / "bin" / "python")
        monkeypatch.setattr(_venv.sys, "executable", venv_python)

        with patch.object(_venv.os, "execve") as execve:
            maybe_reexec_into_project_venv(["arvel", "migrate"])

        execve.assert_not_called()

    def test_no_venv_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text("def create_application(): ...\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(_venv.sys, "executable", "/usr/bin/python3")

        with patch.object(_venv.os, "execve") as execve:
            maybe_reexec_into_project_venv(["arvel", "migrate"])

        execve.assert_not_called()

    def test_outside_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(_venv.sys, "executable", "/usr/bin/python3")

        with patch.object(_venv.os, "execve") as execve:
            maybe_reexec_into_project_venv(["arvel", "make:model", "User"])

        execve.assert_not_called()


class TestExecBranch:
    """``exec_into`` replaces the process on POSIX, spawns + exits on Windows.

    Flipping the global ``os.name`` would make pathlib build WindowsPath on a
    POSIX host, so we exercise ``exec_into`` directly — it never touches pathlib.
    """

    def test_posix_uses_execve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_venv.os, "name", "posix")
        with patch.object(_venv.os, "execve") as execve:
            _venv.exec_into("/v/bin/arvel", ["/v/bin/arvel", "migrate"], {"X": "1"})
        execve.assert_called_once_with("/v/bin/arvel", ["/v/bin/arvel", "migrate"], {"X": "1"})

    def test_windows_spawns_subprocess_and_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_venv.os, "name", "nt")
        completed: Any = MagicMock(returncode=7)
        exe = r"C:\v\Scripts\arvel.exe"
        with (
            patch.object(_venv.subprocess, "run", return_value=completed) as run,
            patch.object(_venv.os, "execve") as execve,
            pytest.raises(SystemExit) as exit_info,
        ):
            _venv.exec_into(exe, [exe, "migrate"], {"X": "1"})

        execve.assert_not_called()
        run.assert_called_once()
        assert exit_info.value.code == 7


class TestEntrypointWiring:
    def test_main_calls_reexec_first(self) -> None:
        import inspect

        import arvel.console.entrypoint as ep

        source = inspect.getsource(ep.main)
        assert "maybe_reexec_into_project_venv" in source

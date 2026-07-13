"""Skeleton sanity: the package imports, the lazy surface behaves, the CLI runs."""

from __future__ import annotations

import subprocess
import sys

import pytest


def test_subpackages_import() -> None:
    import arvel.console
    import arvel.contracts
    import arvel.kernel
    import arvel.support
    from arvel.kernel import Application, ServiceProvider
    from arvel.kernel.provider import KernelServiceProvider

    assert "Container" in arvel.contracts.__all__
    assert "Container" in arvel.kernel.__all__
    assert "Collection" in arvel.support.__all__
    assert issubclass(KernelServiceProvider, ServiceProvider)
    provider = KernelServiceProvider(Application())
    provider.register()
    provider.boot()


def test_lazy_getattr_rejects_unknown() -> None:
    import arvel

    with pytest.raises(AttributeError):
        _ = arvel.DoesNotExist  # type: ignore[attr-defined]


def test_cli_version() -> None:
    import arvel

    # invoke via the venv interpreter, not PATH, which may hold a stray `arvel`.
    proc = subprocess.run(
        [sys.executable, "-m", "arvel.console", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == arvel.__version__

"""The version is single-sourced, and autowiring a bare builtin collection is rejected with a
clear error instead of silently returning an empty one."""

from __future__ import annotations

import pytest

import arvel
from arvel.kernel.application import Application
from arvel.kernel.container import BindingResolutionError, Container


def test_version_is_single_sourced_from_package_metadata() -> None:
    # Application.version() derives from the installed dist version (arvel.__version__) — one source of truth.
    assert Application.version() == arvel.__version__


@pytest.mark.parametrize("builtin", [list, dict, set, frozenset, tuple])
def test_make_rejects_unbound_builtin_collections(builtin: type) -> None:
    with pytest.raises(BindingResolutionError):
        Container().make(builtin)  # was a silent footgun: make(list) -> []

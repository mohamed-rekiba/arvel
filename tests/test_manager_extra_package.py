"""Manager/MissingExtraError — ecosystem packages name their own distribution
in the install hint, not `arvel[...]` (packaging doc: the hint must be the fix)."""

from __future__ import annotations

import pytest

from arvel.support.manager import Manager, MissingExtraError


def test_missing_extra_defaults_to_arvel_distribution() -> None:
    assert "uv add 'arvel[s3]'" in str(MissingExtraError("s3"))


def test_missing_extra_names_a_custom_distribution() -> None:
    err = MissingExtraError("litellm", package="arvel-ai")
    assert "uv add 'arvel-ai[litellm]'" in str(err)


def test_missing_extra_custom_extra_and_package() -> None:
    err = MissingExtraError("temporal", extra="workflows", package="arvel-ai")
    assert "uv add 'arvel-ai[workflows]'" in str(err)


def test_manager_extra_package_hook_flows_into_the_hint() -> None:
    class StripeManager(Manager):
        extra_package = "arvel-stripe"

        def default_driver(self) -> str:
            return "charge"

    with pytest.raises(MissingExtraError) as exc:
        StripeManager().driver()
    assert "uv add 'arvel-stripe[charge]'" in str(exc.value)


def test_manager_default_extra_package_is_arvel() -> None:
    class BareManager(Manager):
        def default_driver(self) -> str:
            return "nope"

    with pytest.raises(MissingExtraError) as exc:
        BareManager().driver()
    assert "uv add 'arvel[nope]'" in str(exc.value)

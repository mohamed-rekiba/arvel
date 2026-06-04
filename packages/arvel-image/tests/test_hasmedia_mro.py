"""Tests for the HasMedia MRO guard.

HasMedia.to_dict() chains via super(). If a base class earlier in the MRO
defines its own to_dict(), HasMedia's never runs and `media` silently drops
from serialization. The guard catches that at class-definition time.

These tests use a small stub base class (not the framework's Model) so the
guard's contract — "fail if any earlier ancestor defines to_dict" — is
exercised in isolation. The condition is universal; testing against the real
Model is redundant once the principle is verified.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel_image.media.trait import HasMedia


class _StubWithToDict:
    """Stand-in for any framework class that provides to_dict (e.g. arvel's Model)."""

    def to_dict(self) -> dict[str, Any]:
        return {"stub": True}


class _StubWithoutToDict:
    """Stand-in for a plain ancestor that doesn't shadow to_dict."""


def test_init_subclass_raises_when_ancestor_with_to_dict_precedes_hasmedia() -> None:
    """A class that puts an ancestor with to_dict before HasMedia is rejected."""
    # type() lets pyright see the dynamic nature — the class object never
    # materializes because __init_subclass__ raises during creation.
    with pytest.raises(TypeError, match="HasMedia must come before"):
        type("_Wrong", (_StubWithToDict, HasMedia), {})


def test_init_subclass_accepts_correct_order() -> None:
    """HasMedia first, then a base with to_dict — chains via super(), guard passes."""

    class _Correct(HasMedia, _StubWithToDict):
        pass

    # No exception; instance creation also succeeds.
    inst = _Correct()
    assert inst.to_dict() == {"stub": True}


def test_init_subclass_accepts_class_without_to_dict_ancestor() -> None:
    """HasMedia alone with a plain ancestor — no chaining needed, no guard fire."""

    class _Plain(HasMedia, _StubWithoutToDict):
        pass

    _Plain()  # Instantiation succeeds.


def test_init_subclass_accepts_hasmedia_only() -> None:
    """Subclassing HasMedia directly — no parent with to_dict, no guard fire."""

    class _Solo(HasMedia):
        pass

    _Solo()


def test_init_subclass_error_names_the_offender() -> None:
    """The TypeError message identifies both the offending class and the base."""
    with pytest.raises(TypeError, match=r"_AlsoWrong.*_StubWithToDict"):
        type("_AlsoWrong", (_StubWithToDict, HasMedia), {})

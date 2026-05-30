"""Resource helper edge cases."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

from arvel.http import resources as resources_module


def test_resource_url_context_handles_missing_and_bad_request_shapes() -> None:
    derive = cast(
        "Callable[[object], tuple[str | None, dict[str, str] | None]]",
        object.__getattribute__(resources_module, "_derive_url_context"),
    )

    assert derive(object()) == (None, None)
    bad_request = SimpleNamespace(url=SimpleNamespace(scheme="https", netloc="", path="/items"))
    assert derive(bad_request) == (None, None)
    request = SimpleNamespace(
        url=SimpleNamespace(scheme="https", netloc="api.test", path="/items"),
        query_params={"page": "2", "cursor": "abc", "filter": "open"},
    )
    assert derive(request) == ("https://api.test/items", {"filter": "open"})


def test_resource_paginator_shape_detection() -> None:
    looks_like = cast(
        "Callable[[Any], bool]",
        object.__getattribute__(resources_module, "_looks_like_paginator"),
    )

    assert looks_like([]) is False
    assert looks_like(SimpleNamespace(items=[1], to_dict=dict)) is True
    assert looks_like(SimpleNamespace(items=[1], to_dict=None)) is False

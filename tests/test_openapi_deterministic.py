"""The exported OpenAPI document must be byte-stable across runs — a codegen/CI drift gate diffs
a fresh export against the committed one, so a route's parameters can't come out in a random order."""

from __future__ import annotations

from typing import Any

from arvel.http import HttpKernel


async def _show(request: Any, id: int, conversion: str) -> dict[str, Any]:
    return {"id": id, "conversion": conversion}


def _params(kernel: HttpKernel, path: str) -> list[dict[str, Any]]:
    doc = kernel.openapi()
    return list(doc["paths"][path]["get"]["parameters"])


def test_multi_param_route_parameters_are_deterministically_ordered() -> None:
    # two path params on one route: the order must be stable and canonical (by `in`, then name),
    # not whatever set/dict iteration Litestar happens to yield this run.
    kernel = HttpKernel()
    kernel.get("/media/{id:int}/{conversion:str}", _show)
    params = _params(kernel, "/media/{id}/{conversion}")
    names = [p["name"] for p in params]
    assert names == sorted(names)  # canonical order
    # stable across a rebuild (a fresh Litestar app each call)
    assert names == [p["name"] for p in _params(kernel, "/media/{id}/{conversion}")]

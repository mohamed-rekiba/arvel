"""H3 — ``RouteDefinition.with_trashed()`` opts a bound param into resolving soft-deleted rows:
without it a soft-deleted model 404s (the default, soft-delete-excluding lookup); with it, the
same id resolves via ``Model.with_trashed()``."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa
from litestar.testing import TestClient

from arvel.database import ConnectionResolver, Model, SoftDeletes
from arvel.http import HttpKernel
from arvel.routing import Router


class TrashedPost(Model, SoftDeletes):
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]


async def _setup() -> tuple[ConnectionResolver, TrashedPost]:
    db = ConnectionResolver()
    TrashedPost.set_connection(db)
    await db.execute(sa.schema.CreateTable(TrashedPost.__table__))
    post = await TrashedPost.create(title="gone")
    await post.delete()  # soft
    return db, post


async def _show(request: Any, post: TrashedPost) -> dict[str, Any]:
    return {"title": post.title}


def _client(router: Router) -> TestClient[Any]:
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


async def test_soft_deleted_binding_404s_by_default() -> None:
    db, post = await _setup()
    try:
        router = Router()
        router.get("/posts/{post}", _show)
        with _client(router) as client:
            assert client.get(f"/posts/{post.id}").status_code == 404
    finally:
        await db.dispose()


async def test_with_trashed_binding_resolves_soft_deleted_row() -> None:
    db, post = await _setup()
    try:
        router = Router()
        router.get("/posts/{post}", _show).with_trashed()
        with _client(router) as client:
            response = client.get(f"/posts/{post.id}")
            assert response.status_code == 200
            assert response.json() == {"title": "gone"}
    finally:
        await db.dispose()


async def test_with_trashed_named_param_only_scopes_that_param() -> None:
    db, post = await _setup()
    try:
        router = Router()
        router.get("/posts/{post}", _show).with_trashed("post")
        with _client(router) as client:
            assert client.get(f"/posts/{post.id}").status_code == 200
    finally:
        await db.dispose()

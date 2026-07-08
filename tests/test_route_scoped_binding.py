"""H2 — scoped implicit bindings: ``/users/{user}/posts/{post}`` resolves ``{post}`` constrained
to ``{user}``'s posts (via ``Model.resolve_child_route_binding``, convention-detected off the
plural relation name) once a route opts in with ``.scope_bindings()``. A post that exists but
belongs to a different user 404s instead of resolving globally; an unscoped route is unchanged."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa
from litestar.testing import TestClient

from arvel.database import ConnectionResolver, Model
from arvel.http import HttpKernel
from arvel.routing import Router


class ScopedUser(Model):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]

    def scoped_posts(self) -> Any:
        return self.has_many(ScopedPost, foreign_key="user_id")


class ScopedPost(Model):
    __fields__: ClassVar = {"title": str, "user_id": int}
    __fillable__: ClassVar = ["title", "user_id"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    ScopedUser.set_connection(db)
    ScopedPost.set_connection(db)
    await db.execute(sa.schema.CreateTable(ScopedUser.__table__))
    await db.execute(sa.schema.CreateTable(ScopedPost.__table__))
    return db


async def _show(request: Any, user: ScopedUser, post: ScopedPost) -> dict[str, Any]:
    return {"user": user.name, "post": post.title}


def _client(router: Router) -> TestClient[Any]:
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


async def test_scoped_binding_resolves_post_belonging_to_user() -> None:
    db = await _setup()
    try:
        ada = await ScopedUser.create(name="Ada")
        post = await ScopedPost.create(title="Hi", user_id=ada.id)

        router = Router()
        router.get("/users/{user}/posts/{post}", _show).scope_bindings()
        with _client(router) as client:
            response = client.get(f"/users/{ada.id}/posts/{post.id}")
            assert response.status_code == 200
            assert response.json() == {"user": "Ada", "post": "Hi"}
    finally:
        await db.dispose()


async def test_scoped_binding_404s_when_post_belongs_to_another_user() -> None:
    db = await _setup()
    try:
        ada = await ScopedUser.create(name="Ada")
        bob = await ScopedUser.create(name="Bob")
        bobs_post = await ScopedPost.create(title="Not yours", user_id=bob.id)

        router = Router()
        router.get("/users/{user}/posts/{post}", _show).scope_bindings()
        with _client(router) as client:
            response = client.get(f"/users/{ada.id}/posts/{bobs_post.id}")
            assert response.status_code == 404
    finally:
        await db.dispose()


async def test_unscoped_route_resolves_post_globally_unchanged() -> None:
    db = await _setup()
    try:
        ada = await ScopedUser.create(name="Ada")
        bob = await ScopedUser.create(name="Bob")
        bobs_post = await ScopedPost.create(title="Not yours", user_id=bob.id)

        router = Router()
        router.get("/users/{user}/posts/{post}", _show)  # no .scope_bindings()
        with _client(router) as client:
            response = client.get(f"/users/{ada.id}/posts/{bobs_post.id}")
            assert response.status_code == 200
            assert response.json() == {"user": "Ada", "post": "Not yours"}
    finally:
        await db.dispose()

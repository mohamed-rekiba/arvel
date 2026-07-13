"""A small project/task API — auth, CRUD, pagination, a relationship, a queued job — assembled through
arvel's production bootstrap and driven over HTTP against live Postgres, Redis, and RabbitMQ.

Uses ``httpx.ASGITransport`` (not litestar's TestClient) so the request handlers, the loop-bound
asyncpg/redis pools, and the in-process queue worker all share the test's single event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, ClassVar

import httpx
import pytest
import sqlalchemy as sa

from arvel import Application, Cache, Model, Route, Schema, abort
from arvel.auth import Authenticatable
from arvel.auth.tokens import ApiToken, TokenGuard, create_token
from arvel.database import SoftDeletes
from arvel.kernel import set_application
from arvel.kernel.bootstrap import bootstrap_app
from arvel.queue import Job
from arvel.security import Hasher

pytestmark = pytest.mark.integration


# --- models (Ref-prefixed to avoid model-registry clashes with other test modules) --
class RefUser(Model, Authenticatable):
    __table_name__ = "ref_users"
    __fields__: ClassVar = {"name": str, "email": str, "password": str}
    __fillable__: ClassVar = ["name", "email", "password"]
    __hidden__: ClassVar = ["password"]
    __casts__: ClassVar = {"password": "hashed"}
    __timestamps__ = True


class RefProject(Model):
    __table_name__ = "ref_projects"
    __fields__: ClassVar = {"name": str, "user_id": int}
    __fillable__: ClassVar = ["name", "user_id"]
    __timestamps__ = True

    def tasks(self) -> Any:
        return self.has_many(RefTask, foreign_key="project_id")


class RefTask(
    Model, SoftDeletes
):  # SoftDeletes: delete() stamps deleted_at; default queries hide it
    __table_name__ = "ref_tasks"
    __fields__: ClassVar = {"title": str, "done": bool, "project_id": int}
    __fillable__: ClassVar = ["title", "done", "project_id"]
    __timestamps__ = True


class RefTaskObserver:
    """Bumps a Redis counter whenever a task is saved — proves observers compose on real infra."""

    async def saved(self, task: Any) -> None:
        await Cache.increment("ref_tasks_observed")


class RefTaskCreatedJob(Job):
    """Bumps a Redis counter — proves the job travels through the real broker."""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id

    async def handle(self) -> None:
        await Cache.increment("ref_tasks_created")


# --- schemas + handlers -------------------------------------------------------------
class Credentials(Schema):
    email: str
    password: str


class ProjectIn(Schema):
    name: str


class TaskIn(Schema):
    title: str


async def _auth(request: Any) -> int:
    user_id = await TokenGuard().user_id(request)
    if user_id is None:
        abort(401, "Unauthenticated")
    return int(user_id)


async def _login(request: Any, data: Credentials) -> Any:
    from arvel.http import Response

    user = await RefUser.where("email", data.email).first()
    if user is None or not Hasher().check(data.password, user.password):
        abort(401, "Invalid credentials")
    token, _ = await create_token(user, name="api")
    return Response(content={"token": token}, status=200)


async def _list_projects(request: Any) -> Any:
    await _auth(request)
    return await RefProject.paginate(per_page=2)


async def _create_project(request: Any, data: ProjectIn) -> Any:
    from arvel.http import Response

    user_id = await _auth(request)
    project = await RefProject.create(name=data.name, user_id=user_id)
    return Response(content={"id": project.id, "name": project.name}, status=201)


async def _show_project(request: Any) -> Any:
    await _auth(request)
    project = await RefProject.find(int(request.path_param("id")))
    if project is None:
        abort(404, "Not found")
    tasks = await project.tasks().get()
    return {"id": project.id, "name": project.name, "tasks": sorted(t.title for t in tasks)}


async def _create_task(request: Any, data: TaskIn) -> Any:
    from arvel.http import Response

    await _auth(request)
    task = await RefTask.create(
        title=data.title, done=False, project_id=int(request.path_param("id"))
    )
    await RefTaskCreatedJob.dispatch(task.id)
    return Response(content={"id": task.id, "title": task.title}, status=201)


def _register_routes() -> None:
    Route.post("/login", _login, name="ref.login")
    Route.get("/projects", _list_projects, name="ref.projects.index")
    Route.post("/projects", _create_project, name="ref.projects.store")
    Route.get("/projects/{id:int}", _show_project, name="ref.projects.show")
    Route.post("/projects/{id:int}/tasks", _create_task, name="ref.tasks.store")


async def test_reference_app_end_to_end(
    postgres_url: str, redis_url: str, rabbitmq_url: str
) -> None:
    app = (
        Application.configure(".")
        .with_config(
            {
                "app": {"key": "base64:" + "A" * 43 + "=", "url": "http://test"},
                "database": {"default": "pgsql", "connections": {"pgsql": {"url": postgres_url}}},
                "cache": {"default": "redis", "url": redis_url},
                "queue": {"default": "amqp", "url": rabbitmq_url},
                "auth": {"defaults": {"guard": "api"}, "guards": {"api": {"driver": "token"}}},
            }
        )
        .create()
    )
    try:
        # setup is inside the try so a failed setup still tears down and doesn't leak the global app
        bootstrap_app(app)
        _register_routes()
        await app.boot()
        db = app.make("db")
        for model in (RefUser, RefProject, RefTask, ApiToken):
            model.set_connection(db)
            await db.execute(sa.schema.CreateTable(model.__table__))
        RefTask.observe(RefTaskObserver())
        await RefUser.create(name="Ada", email="ada@example.com", password="secret123")

        transport = httpx.ASGITransport(app=app.as_asgi())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            assert (
                await c.post("/login", json={"email": "ada@example.com", "password": "x"})
            ).status_code == 401
            assert (await c.get("/projects")).status_code == 401
            tok = (
                await c.post("/login", json={"email": "ada@example.com", "password": "secret123"})
            ).json()["token"]
            h = {"Authorization": f"Bearer {tok}"}

            # a missing required field fails validation → 422 (the body is decoded in the request
            # pipeline, so validation failures are the framework's uniform 422, not a transport 400)
            assert (await c.post("/projects", json={}, headers=h)).status_code == 422
            for name in ("Alpha", "Beta", "Gamma"):
                assert (
                    await c.post("/projects", json={"name": name}, headers=h)
                ).status_code == 201

            page = (await c.get("/projects", headers=h)).json()
            assert page["total"] == 3 and page["per_page"] == 2 and page["last_page"] == 2
            assert len(page["data"]) == 2

            assert (
                await c.post("/projects/1/tasks", json={"title": "T1"}, headers=h)
            ).status_code == 201
            assert (
                await c.post("/projects/1/tasks", json={"title": "T2"}, headers=h)
            ).status_code == 201
            shown = (await c.get("/projects/1", headers=h)).json()
            assert shown["tasks"] == ["T1", "T2"]
            assert (await c.get("/projects/999", headers=h)).status_code == 404

        # observer fires synchronously in-request, so the counter is already 2 here
        assert int(await Cache.get("ref_tasks_observed", 0)) == 2

        loaded = await RefProject.with_("tasks").where("id", "=", 1).first()
        assert loaded is not None
        assert sorted(t.title for t in await loaded.tasks().get()) == ["T1", "T2"]

        task = await RefTask.where("title", "=", "T1").first()
        assert task is not None
        await task.delete()
        assert await RefTask.where("title", "=", "T1").first() is None
        assert await RefTask.with_trashed().where("title", "=", "T1").first() is not None

        worker = asyncio.create_task(app.make("queue").work(release_interval=0.2))
        count = 0
        for _ in range(150):
            count = int(await Cache.get("ref_tasks_created", 0))
            if count >= 2:
                break
            await asyncio.sleep(0.1)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
        assert count == 2, "queued jobs did not run through the real AMQP broker"
    finally:
        # resolve via the container, not the local `db`, so cleanup still runs if setup failed early
        with contextlib.suppress(Exception):
            await app.make("queue").broker.shutdown()
        with contextlib.suppress(Exception):
            await app.make("db").dispose()
        set_application(None)

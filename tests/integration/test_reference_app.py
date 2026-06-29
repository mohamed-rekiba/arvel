"""Integration (doc 20) — a reference app exercised end to end against REAL infrastructure.

This is the brief's "definition of done" in miniature: a small project/task API — token auth, validated
CRUD, pagination, a model relationship, and a queued job — assembled through arvel's **production**
fluent bootstrap and driven over HTTP against a live **PostgreSQL** (models), **Redis** (cache), and
**RabbitMQ** (queue). It proves these features compose on real services, not just in unit fakes.

The app is driven via ``httpx.ASGITransport`` (not litestar's TestClient) so the request handlers, the
loop-bound asyncpg/redis pools, and the in-process queue worker all share the test's single event loop.
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
    """A model observer: bumps a Redis counter whenever a task is saved (proving observers compose on
    real infra — the dispatcher fires, the handler hits the real cache)."""

    async def saved(self, task: Any) -> None:
        await Cache.increment("ref_tasks_observed")


class RefTaskCreatedJob(Job):
    """On task creation, bump a Redis counter — proving the job travels through the real broker and
    its handler reaches the real cache."""

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

    user = await RefUser.query().where("email", data.email).first()
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
        # setup is INSIDE the try so the finally always tears down — a failure here (e.g. leftover
        # ref_* tables from an aborted run) must not leak the global app / asyncpg pool into later tests
        bootstrap_app(app)  # binds the router + discovers framework providers (sync)
        _register_routes()  # facade registration — after the router is bound
        await app.boot()
        db = app.make("db")
        for model in (RefUser, RefProject, RefTask, ApiToken):
            model.set_connection(db)
            await db.execute(sa.schema.CreateTable(model.__table__))
        RefTask.observe(RefTaskObserver())  # wire the observer to RefTask's lifecycle events
        await RefUser.create(name="Ada", email="ada@example.com", password="secret123")

        transport = httpx.ASGITransport(app=app.as_asgi())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # auth: bad creds + no token are rejected; valid creds issue a bearer token
            assert (
                await c.post("/login", json={"email": "ada@example.com", "password": "x"})
            ).status_code == 401
            assert (await c.get("/projects")).status_code == 401
            tok = (
                await c.post("/login", json={"email": "ada@example.com", "password": "secret123"})
            ).json()["token"]
            h = {"Authorization": f"Bearer {tok}"}

            # validation: a missing field is a clean 400, not a 500
            assert (await c.post("/projects", json={}, headers=h)).status_code == 400
            for name in ("Alpha", "Beta", "Gamma"):
                assert (
                    await c.post("/projects", json={"name": name}, headers=h)
                ).status_code == 201

            # pagination against real Postgres
            page = (await c.get("/projects", headers=h)).json()
            assert page["total"] == 3 and page["per_page"] == 2 and page["last_page"] == 2
            assert len(page["data"]) == 2

            # relationship (has_many) + 404
            assert (
                await c.post("/projects/1/tasks", json={"title": "T1"}, headers=h)
            ).status_code == 201
            assert (
                await c.post("/projects/1/tasks", json={"title": "T2"}, headers=h)
            ).status_code == 201
            shown = (await c.get("/projects/1", headers=h)).json()
            assert shown["tasks"] == ["T1", "T2"]
            assert (await c.get("/projects/999", headers=h)).status_code == 404

        # the observer fired on each task save (synchronously, in-request) → Redis counter == 2
        assert int(await Cache.get("ref_tasks_observed", 0)) == 2

        # eager-loading (with_) batches the relation — 2 tasks loaded, no N+1
        loaded = await RefProject.with_("tasks").where("id", "=", 1).first()
        assert loaded is not None
        assert sorted(t.title for t in await loaded.tasks().get()) == ["T1", "T2"]

        # soft deletes: delete() hides the row from default queries but with_trashed() still finds it
        task = await RefTask.where("title", "=", "T1").first()
        assert task is not None
        await task.delete()
        assert await RefTask.where("title", "=", "T1").first() is None  # hidden
        assert await RefTask.with_trashed().where("title", "=", "T1").first() is not None  # soft

        # the two task-create jobs travelled through RabbitMQ; their handler bumped the Redis counter
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
        # defensive: resolve bindings via the container (not the local `db`) so cleanup runs even if
        # setup failed before `db` was assigned; never let a teardown error mask the test outcome
        with contextlib.suppress(Exception):
            await app.make("queue").broker.shutdown()
        with contextlib.suppress(Exception):
            await app.make("db").dispose()
        set_application(None)

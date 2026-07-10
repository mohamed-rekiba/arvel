"""FW-binding-auth-ordering (DR-0054): auth (401) must short-circuit ahead of a missing route-model
binding's 404, closing the zero-credential existence oracle K4 found on ~30 converted admin routes.
Pins both ends of the invariant: a guest gets a uniform 401 whether or not the bound id exists, while
an authenticated+authorized caller still gets the real 404 (including the K4 cross-parent guarantee)."""

from __future__ import annotations

from typing import Any, ClassVar, Self

import sqlalchemy as sa
from litestar.testing import TestClient

from arvel import Application
from arvel.auth.middleware import Authenticate, Authorize, default_aliases
from arvel.database import ConnectionResolver, Model, SoftDeletes
from arvel.http import HttpKernel
from arvel.http.middleware import AuthenticateMiddleware
from arvel.http.response import Response
from arvel.kernel import set_application
from arvel.routing import Router

AUTH_HEADER = {"authorization": "Bearer x"}


class _Widget:
    """A minimal non-DB bindable — mirrors the existing route-binding tests' FakeUser pattern."""

    _rows: ClassVar[dict[str, str]] = {"1": "Gadget"}

    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    async def find(cls, key: Any) -> Self | None:
        name = cls._rows.get(str(key))
        return cls(name) if name is not None else None


async def _show_widget(request: Any, widget: _Widget) -> dict[str, str]:
    return {"name": widget.name}


async def _show_id(request: Any, id: str) -> dict[str, str]:
    return {"id": id}


class _User:
    def __init__(self, *, can: bool = True) -> None:
        self.id = 1
        self._can = can

    async def can(self, ability: str, *args: Any) -> bool:
        return self._can


def _authenticated_kernel(*, can: bool = True) -> HttpKernel:
    """Wired exactly like test_auth_route_middleware's protected-route e2e: global
    AuthenticateMiddleware resolves current_user from an Authorization header; a request without
    the header is a guest and hits whatever route middleware ("auth"/Authenticate) is attached."""
    app = Application()

    def resolver(request: Any) -> _User | None:
        return _User(can=can) if request.header("authorization") else None

    app.instance("user_resolver", resolver)
    set_application(app)
    kernel = HttpKernel()
    kernel.global_middleware = [AuthenticateMiddleware]
    kernel.alias(default_aliases())
    return kernel


# --- the two pinning tests (land first — red/green proves the harness sees real behavior) -----


def test_guest_nonexistent_bound_id_is_401_not_404() -> None:
    """The regression: on main this 404s because binding renders before the pipeline ever runs,
    letting a guest distinguish an existing id from a nonexistent one with zero credentials."""
    kernel = _authenticated_kernel()
    try:
        router = Router()
        router.get("/widgets/{widget}", _show_widget).middleware(Authenticate)
        router.model("widget", _Widget)
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            assert client.get("/widgets/999").status_code == 401
    finally:
        set_application(None)


async def test_authorized_cross_parent_scoped_binding_still_404s() -> None:
    """K4 / DR-0039 guarantee: a real child id that belongs to a different parent must still 404
    for an authorized caller — the deferred-miss change must not weaken this."""
    db = ConnectionResolver()
    ScopedUser.set_connection(db)
    ScopedPost.set_connection(db)
    await db.execute(sa.schema.CreateTable(ScopedUser.__table__))
    await db.execute(sa.schema.CreateTable(ScopedPost.__table__))
    try:
        ada = await ScopedUser.create(name="Ada")
        bob = await ScopedUser.create(name="Bob")
        bobs_post = await ScopedPost.create(title="Not yours", user_id=bob.id)

        kernel = _authenticated_kernel()
        try:
            router = Router()
            router.get("/scoped-users/{user}/posts/{post}", _show_scoped).middleware(
                Authenticate
            ).scope_bindings()
            router.apply_to(kernel)
            with TestClient(kernel.build()) as client:
                response = client.get(
                    f"/scoped-users/{ada.id}/posts/{bobs_post.id}", headers=AUTH_HEADER
                )
                assert response.status_code == 404
        finally:
            set_application(None)
    finally:
        await db.dispose()


# --- rest of the acceptance matrix (spec: FW-binding-auth-ordering) ----------------------------


def test_guest_existing_bound_id_is_401_uniform_with_nonexistent() -> None:
    kernel = _authenticated_kernel()
    try:
        router = Router()
        router.get("/widgets/{widget}", _show_widget).middleware(Authenticate)
        router.model("widget", _Widget)
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            assert client.get("/widgets/1").status_code == 401
    finally:
        set_application(None)


def test_authorized_but_unauthorized_existing_id_is_403_unchanged() -> None:
    kernel = _authenticated_kernel(can=False)
    try:
        router = Router()
        router.get("/widgets/{widget}", _show_widget).middleware(
            Authenticate, Authorize("widgets.view")
        )
        router.model("widget", _Widget)
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            assert client.get("/widgets/1", headers=AUTH_HEADER).status_code == 403
    finally:
        set_application(None)


def test_authorized_nonexistent_bound_id_is_404() -> None:
    kernel = _authenticated_kernel()
    try:
        router = Router()
        router.get("/widgets/{widget}", _show_widget).middleware(Authenticate)
        router.model("widget", _Widget)
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            assert client.get("/widgets/999", headers=AUTH_HEADER).status_code == 404
    finally:
        set_application(None)


def test_authorized_valid_id_returns_200_with_resolved_model() -> None:
    kernel = _authenticated_kernel()
    try:
        router = Router()
        router.get("/widgets/{widget}", _show_widget).middleware(Authenticate)
        router.model("widget", _Widget)
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            response = client.get("/widgets/1", headers=AUTH_HEADER)
            assert response.status_code == 200
            assert response.json() == {"name": "Gadget"}
    finally:
        set_application(None)


def test_missing_callback_deferred_past_auth() -> None:
    """The custom .missing() response must not leak model-existence to a guest — it only fires
    once auth passes, exactly like the default 404 does."""
    calls: list[str] = []

    def custom_missing(request: Any) -> Any:
        calls.append("fired")
        return Response({"custom": "not here"}, status=404)

    kernel = _authenticated_kernel()
    try:
        router = Router()
        router.get("/widgets/{widget}", _show_widget).middleware(Authenticate).missing(
            custom_missing
        )
        router.model("widget", _Widget)
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            guest_response = client.get("/widgets/999")
            assert guest_response.status_code == 401
            assert calls == []  # the callback did not fire for the guest

            authed_response = client.get("/widgets/999", headers=AUTH_HEADER)
            assert authed_response.status_code == 404
            assert authed_response.json() == {"custom": "not here"}
            assert calls == ["fired"]
    finally:
        set_application(None)


def test_where_mismatch_still_404s_before_auth() -> None:
    """A URL-shape constraint is not an existence signal — .where() keeps 404ing ahead of auth,
    unaffected by deferring the *binding* miss."""
    kernel = _authenticated_kernel()
    try:
        router = Router()
        router.get("/numbers/{id}", _show_id).middleware(Authenticate).where("id", r"\d+")
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            assert client.get("/numbers/abc").status_code == 404
    finally:
        set_application(None)


def test_deferred_404_content_negotiates_identically_to_before() -> None:
    """render_exception is the single propagation path whether an HttpException(404) is raised
    from _dispatch (today) or from inside the pipeline's destination (after the fix) — so a JSON
    client still gets a JSON body and an HTML client still gets the HTML error page."""
    kernel = _authenticated_kernel()
    try:
        router = Router()
        router.get("/widgets/{widget}", _show_widget).middleware(Authenticate)
        router.model("widget", _Widget)
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            json_response = client.get(
                "/widgets/999", headers={**AUTH_HEADER, "accept": "application/json"}
            )
            assert json_response.status_code == 404
            assert json_response.headers["content-type"].startswith("application/json")

            html_response = client.get(
                "/widgets/999", headers={**AUTH_HEADER, "accept": "text/html"}
            )
            assert html_response.status_code == 404
            assert html_response.headers["content-type"].startswith("text/html")
    finally:
        set_application(None)


class TrashedWidget(Model, SoftDeletes):
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]


async def _show_trashed(request: Any, widget: TrashedWidget) -> dict[str, Any]:
    return {"title": widget.title}


async def test_with_trashed_still_resolves_for_an_authorized_caller() -> None:
    """with_trashed/domain-param resolution is untouched by the ordering fix (design doc
    invariant); confirm it still works once the route also carries the auth middleware."""
    db = ConnectionResolver()
    TrashedWidget.set_connection(db)
    await db.execute(sa.schema.CreateTable(TrashedWidget.__table__))
    try:
        widget = await TrashedWidget.create(title="gone")
        await widget.delete()  # soft

        kernel = _authenticated_kernel()
        try:
            router = Router()
            router.get("/trashed/{widget}", _show_trashed).middleware(Authenticate).with_trashed()
            router.apply_to(kernel)
            with TestClient(kernel.build()) as client:
                response = client.get(f"/trashed/{widget.id}", headers=AUTH_HEADER)
                assert response.status_code == 200
                assert response.json() == {"title": "gone"}
        finally:
            set_application(None)
    finally:
        await db.dispose()


class ScopedUser(Model):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]

    def scoped_posts(self) -> Any:
        return self.has_many(ScopedPost, foreign_key="user_id")


class ScopedPost(Model):
    __fields__: ClassVar = {"title": str, "user_id": int}
    __fillable__: ClassVar = ["title", "user_id"]


async def _show_scoped(request: Any, user: ScopedUser, post: ScopedPost) -> dict[str, Any]:
    return {"user": user.name, "post": post.title}

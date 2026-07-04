"""arvel.routing — the Route registrar.

Collects route definitions (method/path/handler/name) with prefix + name groups
and compiles them onto the :class:`~arvel.http.kernel.HttpKernel` (which adapts
them onto Litestar). Provides named-route URL generation. The Litestar compile
itself lives in the HTTP kernel; routing stays engine-agnostic.

Grounded in knowledge/port/05-routing.md.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence
    from pathlib import Path

    from arvel.http.kernel import HttpKernel


_RESOURCE_ACTIONS: list[tuple[str, list[str], str]] = [
    ("index", ["GET"], ""),
    ("create", ["GET"], "/create"),
    ("store", ["POST"], ""),
    ("show", ["GET"], "/{id}"),
    ("edit", ["GET"], "/{id}/edit"),
    ("update", ["PUT", "PATCH"], "/{id}"),
    ("destroy", ["DELETE"], "/{id}"),
]


# RESTful action → (policy ability, needs a model instance) (Laravel authorizeResource map).
_ACTION_ABILITIES: dict[str, tuple[str, bool]] = {
    "index": ("viewAny", False),
    "create": ("create", False),
    "store": ("create", False),
    "show": ("view", True),
    "edit": ("update", True),
    "update": ("update", True),
    "destroy": ("delete", True),
}


class Controller:
    """Base controller. Subclass with async action methods — ``index``/``show``/
    ``store``/``update``/``destroy`` (+ ``create``/``edit`` for web resources) — and
    register them in one call via ``Router.resource(name, Controller)``."""

    __resource_policy__: ClassVar[type | None] = None

    @classmethod
    def authorize_resource(cls, model: type) -> None:
        """Authorize every resource action against ``model``'s policy automatically (Laravel
        ``authorizeResource``): ``index``→``viewAny``, ``show``→``view``, ``store``→``create``,
        ``update``→``update``, ``destroy``→``delete``. Instance abilities authorize against the
        route-bound model; class abilities against the model itself. 403 (``AuthorizationError``)
        on denial, before the action runs."""
        cls.__resource_policy__ = model


def _guard_action(handler: Any, action: str, model: type, param: str) -> Any:
    """Wrap a resource action so its policy ability is authorized before the handler runs."""
    import functools

    ability, needs_instance = _ACTION_ABILITIES[action]

    @functools.wraps(handler)
    async def guarded(*args: Any, **kwargs: Any) -> Any:
        from arvel.kernel import app, has_application

        if has_application() and app().bound("gate"):
            target = kwargs.get(param) if needs_instance else None
            await app("gate").authorize(ability, target if target is not None else model)
        return await handler(*args, **kwargs)

    return guarded


@dataclass
class RouteDefinition:
    methods: list[str]
    path: str
    handler: Any
    name: str | None = None
    is_fallback: bool = False
    group: str | None = None  # named middleware group (e.g. "web"/"api") to run for this route
    middlewares: list[Any] = field(
        default_factory=list[Any]
    )  # per-route middleware (Laravel ->middleware)
    security: list[str] = field(
        default_factory=list[str]
    )  # OpenAPI security schemes this route requires (e.g. "bearer")
    status_code: int | None = None  # explicit response status (else Litestar's per-method default)

    def status(self, code: int) -> RouteDefinition:
        """Pin this route's success response status (Laravel ``response()->json($x, 200)``). Lets a
        typed-Schema POST return 200 instead of Litestar's default 201 (e.g. a login/logout action
        that isn't *creating* a resource)."""
        self.status_code = code
        return self

    def middleware(self, *mw: Any) -> RouteDefinition:
        """Attach per-route middleware (Laravel ``Route::get(...)->middleware('auth')``).
        Runs after global + group middleware (global → group → route)."""
        self.middlewares.extend(mw)
        return self

    def secure(self, *schemes: str) -> RouteDefinition:
        """Mark this route as requiring an OpenAPI security scheme (default ``"bearer"``) — it shows
        the lock + 'Authorize' requirement in the API docs. Documents the contract; enforcement is
        still the handler's/middleware's job. The scheme must be defined in ``config('openapi').security``."""
        self.security.extend(schemes or ("bearer",))
        return self


class Router:
    """Fluent route registrar with prefix/name groups and URL generation."""

    def __init__(self) -> None:
        self._routes: list[RouteDefinition] = []
        self._prefix = ""
        self._name_prefix = ""
        self._middleware: list[Any] = []  # middleware from the current group stack
        self._group: str | None = None  # named group from the current group stack
        self._bindings: dict[str, Any] = {}

    def add(
        self, methods: Sequence[str], path: str, handler: Any, name: str | None = None
    ) -> RouteDefinition:
        route = RouteDefinition(
            methods=[m.upper() for m in methods],
            path=self._prefix + path,
            handler=handler,
            name=(self._name_prefix + name) if name else None,
            group=self._group,
            middlewares=list(self._middleware),
        )
        self._routes.append(route)
        return route

    def get(self, path: str, handler: Any, name: str | None = None) -> RouteDefinition:
        return self.add(["GET"], path, handler, name)

    def post(self, path: str, handler: Any, name: str | None = None) -> RouteDefinition:
        return self.add(["POST"], path, handler, name)

    def put(self, path: str, handler: Any, name: str | None = None) -> RouteDefinition:
        return self.add(["PUT"], path, handler, name)

    def patch(self, path: str, handler: Any, name: str | None = None) -> RouteDefinition:
        return self.add(["PATCH"], path, handler, name)

    def delete(self, path: str, handler: Any, name: str | None = None) -> RouteDefinition:
        return self.add(["DELETE"], path, handler, name)

    def match(
        self, methods: Sequence[str], path: str, handler: Any, name: str | None = None
    ) -> RouteDefinition:
        """Bind a route to several HTTP verbs at once (Laravel ``Route::match``)."""
        return self.add(methods, path, handler, name)

    def any(self, path: str, handler: Any, name: str | None = None) -> RouteDefinition:
        """Bind a route to all standard verbs (Laravel ``Route::any``)."""
        return self.add(["GET", "POST", "PUT", "PATCH", "DELETE"], path, handler, name)

    def resource(
        self,
        name: str,
        controller: Any,
        *,
        only: Sequence[str] | None = None,
        except_: Sequence[str] | None = None,
        api: bool = False,
    ) -> Router:
        """Register the 7 RESTful routes (Laravel ``Route::resource``) for a controller.

        Only actions the controller actually implements are bound. ``api=True`` drops
        the HTML-form actions (``create``/``edit``). ``only``/``except_`` narrow the set.
        """
        from arvel.support import Str

        instance = controller() if isinstance(controller, type) else controller
        param = Str.snake(Str.singular(name.strip("/").split("/")[-1]))
        base = "/" + name.strip("/")
        excluded = {"create", "edit"} if api else set[str]()
        for action, methods, suffix in _RESOURCE_ACTIONS:
            if action in excluded:
                continue
            if only is not None and action not in only:
                continue
            if except_ is not None and action in except_:
                continue
            handler = getattr(instance, action, None)
            if handler is None:
                continue
            policy = getattr(instance, "__resource_policy__", None)
            if policy is not None and action in _ACTION_ABILITIES:
                handler = _guard_action(handler, action, policy, param)
            path = base + suffix.replace("{id}", "{" + param + "}")
            self.add(methods, path, handler, name=f"{name}.{action}")
        return self

    def api_resource(
        self,
        name: str,
        controller: Any,
        *,
        only: Sequence[str] | None = None,
        except_: Sequence[str] | None = None,
    ) -> Router:
        """Register the 5 API resource routes (no ``create``/``edit`` form actions)."""
        return self.resource(name, controller, only=only, except_=except_, api=True)

    def fallback(self, handler: Any, name: str | None = None) -> RouteDefinition:
        """Register a catch-all route (Laravel ``Route::fallback``)."""
        route = self.add(["GET"], "/{fallback_path:path}", handler, name or "fallback")
        route.is_fallback = True
        return route

    def public(
        self,
        directory: str | Path,
        *,
        path: str = "/",
        assets_dirname: str = "assets",
        spa_fallback: bool = True,
    ) -> Router:
        """Serve ``directory`` as the app's public web root — Laravel's ``public/``: the ONE
        directory a webserver exposes (``index.php`` there is the front controller; everything
        else — ``app/``, ``routes/``, ``.env``, ``storage/`` — sits outside it and is never
        directly reachable). arvel has no separate webserver in front to split "a real file →
        serve it directly" from "everything else → the app," so this registers that split as ASGI
        routes instead: a request whose path matches a real file under ``directory`` (favicon.ico,
        robots.txt, a published ``storage`` symlink target, a bundler's build output, ...) gets
        that file back as-is. Anything under ``assets_dirname`` is assumed content-hashed by a
        frontend bundler (Vite/webpack/... all use this convention) and is cached forever;
        everything else stays revalidate-able so a new deploy is picked up without a hard
        cache-bust.

        ``spa_fallback`` (default ``True``) decides what happens when a path ISN'T a real file.
        Most arvel apps embed a client-side-routed frontend, so by default it falls back to
        ``directory/index.html`` and lets that router (history-mode) decide what to render — the
        same trick as Laravel's own OPTIONAL catch-all ``Route::get('/{any}', ...)->where('any',
        '.*')`` or Nginx's ``try_files $uri $uri/ /index.html``. It's optional in Laravel too — a
        server-rendered (Blade/Inertia-SSR) or API-only app has no such route. Pass
        ``spa_fallback=False`` for those: only real files under ``directory`` are ever served
        (favicon/robots/storage/...), and an unmatched path 404s normally rather than claiming
        ``/`` or any other path your app already owns.

        With ``spa_fallback=True``, both registered routes are marked ``is_fallback``
        (:meth:`apply_to` sorts those last), so this is safe to call before OR after your other
        routes — a more specific route (``/api/*``, an admin group, ...) always wins on its own
        path regardless of registration order.
        """
        from pathlib import Path as _Path

        root = _Path(directory).resolve()

        def _real_file(rel: str) -> _Path | None:
            requested = (root / rel.lstrip("/")).resolve()
            return requested if requested.is_relative_to(root) and requested.is_file() else None

        async def _to_response(target: _Path) -> Any:
            from mimetypes import guess_type

            from arvel.http.exceptions import abort
            from arvel.http.response import Response

            if not target.is_file():
                # spa_fallback's own index.html is missing (public/ not built) -> a clear error
                # instead of a raw FileNotFoundError surfacing as an opaque 500
                abort(500, f"public directory has no index.html — did you build it? ({target})")
            immutable = target.parent.name == assets_dirname
            content_type = guess_type(target.name)[0] or "application/octet-stream"
            cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
            return Response(
                content=target.read_bytes(),
                status=200,
                headers={"content-type": content_type, "cache-control": cache},
            )

        if spa_fallback:
            # two thin handlers, not one shared function with an optional `path`: the root route's
            # template has no `{path}` placeholder, so a shared `path` param would be wrongly
            # inferred as a documented query parameter on that route
            async def _serve_root(request: Any) -> Any:
                return await _to_response(_real_file("") or root / "index.html")

            async def _serve_catchall(request: Any, path: str) -> Any:
                return await _to_response(_real_file(path) or root / "index.html")

            root_route = self.add(["GET"], path, _serve_root, "public.root")
            root_route.is_fallback = True
            catchall_route = self.add(
                ["GET"], path.rstrip("/") + "/{path:path}", _serve_catchall, "public"
            )
            catchall_route.is_fallback = True
        else:
            from arvel.http.exceptions import abort

            async def _serve_static(request: Any, path: str) -> Any:
                found = _real_file(path)
                if found is None:
                    abort(404, "Not found")
                return await _to_response(found)

            static_route = self.add(
                ["GET"], path.rstrip("/") + "/{path:path}", _serve_static, "public"
            )
            static_route.is_fallback = True
        return self

    def redirect(
        self, uri: str, destination: str, status: int = 302, name: str | None = None
    ) -> RouteDefinition:
        """A GET route that redirects to ``destination`` (Laravel ``Route::redirect``)."""
        from arvel.http.response import Response

        async def handler(request: Any) -> Response:
            return Response(status=status, headers={"Location": destination})

        return self.add(["GET"], uri, handler, name)

    def permanent_redirect(
        self, uri: str, destination: str, name: str | None = None
    ) -> RouteDefinition:
        """A 301 redirect route (Laravel ``Route::permanentRedirect``)."""
        return self.redirect(uri, destination, status=301, name=name)

    def view(
        self, uri: str, view_name: str, data: dict[str, Any] | None = None, name: str | None = None
    ) -> RouteDefinition:
        """A GET route that renders a view with no controller (Laravel ``Route::view``)."""
        from arvel.views import view as render_view

        async def handler(request: Any) -> Any:
            return await render_view(view_name, data or {}).to_response()

        return self.add(["GET"], uri, handler, name)

    # --- route-model / enum binding -----------------------------------------
    def model(self, param: str, model: Any, key: str | None = None) -> Router:
        """Route-model binding: ``{param}`` resolves to a model (404 on miss). Default binds
        by primary key via ``Model.find``; pass ``key`` for a custom route key — e.g.
        ``model("post", Post, key="slug")`` resolves ``{post}`` via ``Post.where(slug=...)``."""
        if key is None:
            self._bindings[param] = model.find
        else:

            async def binder(value: Any) -> Any:
                return await model.where(key, "=", value).first()

            self._bindings[param] = binder
        return self

    def bind(self, param: str, resolver: Any) -> Router:
        """Explicit binding: ``{param}`` resolves via ``resolver(value)`` (sync or async)."""
        self._bindings[param] = resolver
        return self

    def bind_enum(self, param: str, enum_cls: Any) -> Router:
        """Enum binding: coerce ``{param}`` to an enum member (404 on an invalid value)."""

        def binder(value: Any) -> Any:
            try:
                return enum_cls(value)
            except ValueError:
                return None

        self._bindings[param] = binder
        return self

    @contextlib.contextmanager
    def group(
        self,
        prefix: str = "",
        name: str = "",
        middleware: Sequence[Any] | None = None,
        group: str | None = None,
    ) -> Generator[Router]:
        """Open a route group. ``prefix``/``name`` extend the path and name prefixes;
        ``middleware`` adds middleware run for every route in the block; ``group`` assigns
        a named kernel middleware group (e.g. ``"web"``/``"api"``). Nested groups compose
        (outer + inner middleware both run) and restore on exit."""
        previous = (self._prefix, self._name_prefix, self._middleware, self._group)
        self._prefix += prefix
        self._name_prefix += name
        self._middleware = [*self._middleware, *(middleware or [])]
        if group is not None:
            self._group = group
        try:
            yield self
        finally:
            self._prefix, self._name_prefix, self._middleware, self._group = previous

    def routes(self) -> list[RouteDefinition]:
        return list(self._routes)

    def url(self, name: str, **params: Any) -> str:
        """Generate a URL for a named route (Laravel ``route()``). Path placeholders
        ``{param}`` are filled from ``params``; any leftover params are appended as a
        URL-encoded query string. Raises ``ValueError`` if a required path param is
        missing, ``KeyError`` if no route has that name."""
        import re
        from urllib.parse import urlencode

        for route in self._routes:
            if route.name == name:
                path = route.path
                query: dict[str, Any] = {}
                for key, value in params.items():
                    placeholder = "{" + key + "}"
                    if placeholder in path:
                        path = path.replace(placeholder, str(value))
                    else:
                        query[key] = value
                unfilled = re.findall(r"\{(\w+)\}", path)
                if unfilled:
                    raise ValueError(
                        f"Missing route parameter(s) {unfilled} generating URL for {name!r}"
                    )
                if query:
                    path += ("&" if "?" in path else "?") + urlencode(query)
                return path
        raise KeyError(f"No route named {name!r}")

    @staticmethod
    def _signing_key(key: str | None) -> str:
        """The signing key — an explicit ``key`` or, by default, the app key (``config('app.key')``,
        Laravel parity). Raises a clear error if neither is available."""
        if key is not None:
            return key
        from arvel.kernel import app, has_application

        app_key = app("config").get("app.key") if has_application() else None
        if not app_key:
            raise RuntimeError(
                "signed URLs need a key: pass key=, or set config('app.key') (APP_KEY)."
            )
        return str(app_key)

    def signed_url(
        self, name: str, *, key: str | None = None, expires: int | None = None, **params: Any
    ) -> str:
        """A tamper-evident URL for a named route (Laravel ``URL::signedRoute``).

        ``expires`` (a unix timestamp) makes it temporary. The signature is an itsdangerous MAC over
        the URL, appended as a ``signature`` query param. ``key`` defaults to the app key.
        """
        from arvel.security import Signer

        url = self.url(name, **params)
        if expires is not None:
            url += ("&" if "?" in url else "?") + f"expires={expires}"
        token = Signer(self._signing_key(key)).sign(url)
        return url + ("&" if "?" in url else "?") + f"signature={token}"

    def has_valid_signature(self, url: str, *, key: str | None = None) -> bool:
        """Verify a ``signed_url`` (integrity + ``expires`` not in the past). ``key`` defaults to the
        app key."""
        import time

        from arvel.security import Signer

        if "signature=" not in url:
            return False
        key = self._signing_key(key)
        base, _, token = url.rpartition("signature=")
        base = base.rstrip("?&")
        try:
            if Signer(key).unsign(token) != base:
                return False
        except Exception:
            return False
        marker = "expires="
        if marker in base:
            expires = int(base.rpartition(marker)[2].split("&")[0])
            if expires < int(time.time()):
                return False
        return True

    def apply_to(self, kernel: HttpKernel) -> None:
        # Fallback (catch-all) routes are registered last so concrete routes win.
        ordered = sorted(self._routes, key=lambda route: route.is_fallback)
        for route in ordered:
            kernel.add_route(
                route.methods,
                route.path,
                route.handler,
                group=route.group,
                middleware=route.middlewares,
                name=route.name,
                security=route.security,
                status_code=route.status_code,
            )
        kernel.bindings.update(self._bindings)


__all__ = ["Controller", "RouteDefinition", "Router"]

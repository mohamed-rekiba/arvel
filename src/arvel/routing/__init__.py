"""arvel.routing — the Route registrar.

Collects route definitions (method/path/handler/name) with prefix + name groups
and compiles them onto the:class:`~arvel.http.kernel.HttpKernel` (which adapts
them onto Litestar). Provides named-route URL generation. The Litestar compile
itself lives in the HTTP kernel; routing stays engine-agnostic.

Grounded in knowledge/port/05-routing.md.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence
    from pathlib import Path

    from arvel.http.kernel import HttpKernel
    from arvel.http.redirect import Redirect
    from arvel.http.request import RouteMatch
    from arvel.routing.broadcast_relay import broadcast_websocket as broadcast_websocket
    from arvel.routing.broadcasting_auth import verify_channel_auth as verify_channel_auth


_RESOURCE_ACTIONS: list[tuple[str, list[str], str]] = [
    ("index", ["GET"], ""),
    ("create", ["GET"], "/create"),
    ("store", ["POST"], ""),
    ("show", ["GET"], "/{id}"),
    ("edit", ["GET"], "/{id}/edit"),
    ("update", ["PUT", "PATCH"], "/{id}"),
    ("destroy", ["DELETE"], "/{id}"),
]


# RESTful action → (policy ability, needs a model instance).
_ACTION_ABILITIES: dict[str, tuple[str, bool]] = {
    "index": ("viewAny", False),
    "create": ("create", False),
    "store": ("create", False),
    "show": ("view", True),
    "edit": ("update", True),
    "update": ("update", True),
    "destroy": ("delete", True),
}


@dataclass
class ControllerMiddleware:
    """One entry of ``Controller.middleware()``: ``middleware`` is
    anything a route accepts (an alias string, a ``throttle:name`` string, or a middleware
    class/instance); ``only``/``except_`` narrow it to specific resource actions."""

    middleware: Any
    only: tuple[str, ...] = ()
    except_: tuple[str, ...] = ()

    def applies_to(self, action: str) -> bool:
        if self.only and action not in self.only:
            return False
        return action not in self.except_


class Controller:
    """Base controller. Subclass with async action methods — ``index``/``show``/
    ``store``/``update``/``destroy`` (+ ``create``/``edit`` for web resources) — and
    register them in one call via ``Router.resource(name, Controller)``."""

    __resource_policy__: ClassVar[type | None] = None

    @classmethod
    def middleware(cls) -> list[ControllerMiddleware]:
        """Controller-level middleware: override to return
        ``ControllerMiddleware(name, only=(...), except_=(...))`` entries — honored by
        ``Router.resource``/``api_resource``, applied per bound action."""
        return []

    @classmethod
    def authorize_resource(cls, model: type) -> None:
        """Authorize every resource action against ``model``'s policy automatically (``authorizeResource``): ``index``→``viewAny``, ``show``→``view``, ``store``→``create``,
        ``update``→``update``, ``destroy``→``delete``. Instance abilities authorize against the
        route-bound model; class abilities against the model itself. 403 (``AuthorizationError``)
        on denial, before the action runs.

        Prefer the declarative form — set ``__resource_policy__ = Model`` in the class body,
        beside ``middleware()`` — over calling this after the class definition; both are
        equivalent (this method just sets that attribute)."""
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
    middlewares: list[Any] = field(default_factory=list[Any])  # per-route middleware
    security: list[str] = field(
        default_factory=list[str]
    )  # OpenAPI security schemes this route requires (e.g. "bearer")
    status_code: int | None = None  # explicit response status (else Litestar's per-method default)
    wheres: dict[str, str] = field(default_factory=dict[str, str])  # param -> regex constraint
    # custom response when a bound param fails to resolve
    missing_callback: Callable[[Any], Any] | None = None
    excluded_middleware: list[Any] = field(default_factory=list[Any])  # `.without_middleware()`
    domain: str | None = None  # host pattern (H1) — may contain a `{param}` segment
    scoped: bool = False  # `.scope_bindings()` — resolve implicit child bindings within the parent
    trashed_all: bool = False  # `.with_trashed()` with no args — every bound param on this route
    trashed_params: set[str] = field(default_factory=set[str])  # `.with_trashed(*params)`
    include_in_schema: bool = True  # `.hidden()` drops it from the OpenAPI document

    def hidden(self) -> RouteDefinition:
        """Keep this route out of the generated OpenAPI document (and the docs UI). For operational
        endpoints that aren't part of the API contract — health/liveness probes, webhooks, internal
        callbacks — that orchestrators or infrastructure call, not API clients. The route still
        works; it just isn't advertised in the schema."""
        self.include_in_schema = False
        return self

    def status(self, code: int) -> RouteDefinition:
        """Pin this route's success response status. Lets a
        typed-Schema POST return 200 instead of Litestar's default 201 (e.g. a login/logout action
        that isn't *creating* a resource)."""
        self.status_code = code
        return self

    def middleware(self, *mw: Any) -> RouteDefinition:
        """Attach per-route middleware.
        Runs after global + group middleware (global → group → route)."""
        self.middlewares.extend(mw)
        return self

    def without_middleware(self, *mw: Any) -> RouteDefinition:
        """Exclude ``mw`` (a class, instance, or alias string) from the global/group/route stack
        that would otherwise run for this route — e.g. a public route inside an otherwise
        CSRF-protected ``web`` group."""
        self.excluded_middleware.extend(mw)
        return self

    def where(self, param: str, pattern: str) -> RouteDefinition:
        """Constrain ``{param}`` to match the regex ``pattern``; a request whose captured segment
        doesn't match renders 404 instead of reaching the handler."""
        self.wheres[param] = pattern
        return self

    def missing(self, callback: Callable[[Any], Any]) -> RouteDefinition:
        """``callback(request)`` builds the response when this route's model binding (explicit or
        implicit) fails to resolve, instead of the default 404."""
        self.missing_callback = callback
        return self

    def scope_bindings(self, enabled: bool = True) -> RouteDefinition:
        """Opt this route's implicit bindings into parent-scoped resolution (H2): once a param
        resolves to a model, a later param resolves through ``resolve_child_route_binding`` —
        constrained to that parent's relation (named for the child's plural snake name, e.g.
        ``Post`` -> ``posts``) instead of a global lookup, so
        ``/users/{user}/posts/{post}`` 404s a real post id that belongs to someone else. A child
        model with no matching relation just resolves globally, same as an unscoped route."""
        self.scoped = enabled
        return self

    def with_trashed(self, *params: str) -> RouteDefinition:
        """Opt bound param(s) into resolving soft-deleted rows too — the default binding lookup
        404s them. No args opts in every bound param on this route; named args opt in only those."""
        if params:
            self.trashed_params.update(params)
        else:
            self.trashed_all = True
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
        self._websockets: list[tuple[str, Any, str | None]] = []  # (path, handler, name)
        self._prefix = ""
        self._name_prefix = ""
        self._middleware: list[Any] = []  # middleware from the current group stack
        self._security: list[str] = []  # OpenAPI security schemes from the current group stack
        self._group: str | None = None  # named group from the current group stack
        self._domain: str | None = None  # host pattern from the current group stack (H1)
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
            security=list(self._security),
            domain=self._domain,
        )
        self._routes.append(route)
        return route

    def websocket(self, path: str, handler: Any, name: str | None = None) -> None:
        """Register a websocket route. ``handler`` is ``async def(socket)`` receiving the connection
        (``accept``/``receive_text``/``send_text``/``iter_data``/``close``). Honors the current
        prefix/name group; runs outside the HTTP middleware pipeline (a socket has no request cycle).
        For realtime broadcast fan-out, ``arvel.routing.broadcast_websocket`` is a ready handler."""
        self._websockets.append(
            (self._prefix + path, handler, (self._name_prefix + name) if name else None)
        )

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
        """Bind a route to several HTTP verbs at once."""
        return self.add(methods, path, handler, name)

    def any(self, path: str, handler: Any, name: str | None = None) -> RouteDefinition:
        """Bind a route to all standard verbs."""
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
        """Register the 7 RESTful routes for a controller.

        Only actions the controller actually implements are bound. ``api=True`` drops
        the HTML-form actions (``create``/``edit``). ``only``/``except_`` narrow the set.
        """
        from arvel.support import Str

        if isinstance(controller, type):
            # `Route::apiResource('posts', PostController::class)` parity: pass the CLASS and
            # the framework instantiates — through the container when the app is up, so the
            # controller's constructor dependencies resolve exactly like an invokable handler's.
            from arvel.kernel.globals import app, has_application

            instance = app().make(controller) if has_application() else controller()
        else:
            instance = controller
        controller_middleware = (
            list(instance.middleware()) if hasattr(instance, "middleware") else []
        )
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
            route = self.add(methods, path, handler, name=f"{name}.{action}")
            for entry in controller_middleware:
                if entry.applies_to(action):
                    route.middleware(entry.middleware)
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
        """Register a catch-all route."""
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
        """Serve ``directory`` as the app's public web root — the ``public/``: the ONE
        directory a webserver exposes (``index.php`` there is the front controller; everything
        else — ``app/``, ``routes/``, ``.env``, ``storage/`` — sits outside it and is never
        directly reachable). arvel has no separate webserver in front to split "a real file →
        serve it directly" from "everything else → the app," so this registers that split as ASGI
        routes instead: a request whose path matches a real file under ``directory`` (favicon.ico,
        robots.txt, a published ``storage`` symlink target, a bundler's build output,...) gets
        that file back as-is. Anything under ``assets_dirname`` is assumed content-hashed by a
        frontend bundler (Vite/webpack/... all use this convention) and is cached forever;
        everything else stays revalidate-able so a new deploy is picked up without a hard
        cache-bust.

        ``spa_fallback`` (default ``True``) decides what happens when a path ISN'T a real file.
        Most arvel apps embed a client-side-routed frontend, so by default it falls back to
        ``directory/index.html`` and lets that router (history-mode) decide what to render — the
        same trick as the own OPTIONAL catch-all ``Route::get('/{any}',...)->where('any',
        '.*')`` or Nginx's ``try_files $uri $uri/ /index.html``. It's optional in too — a
        server-rendered or API-only app has no such route. Pass
        ``spa_fallback=False`` for those: only real files under ``directory`` are ever served
        (favicon/robots/storage/...), and an unmatched path 404s normally rather than claiming
        ``/`` or any other path your app already owns.

        With ``spa_fallback=True``, both registered routes are marked ``is_fallback``
        (:meth:`apply_to` sorts those last), so this is safe to call before OR after your other
        routes — a more specific route (``/api/*``, an admin group,...) always wins on its own
        path regardless of registration order.
        """
        from pathlib import Path as _Path

        root = _Path(directory).resolve()

        def _locate(rel: str, fallback: bool) -> tuple[str, Any]:
            """Resolve, traversal-guard, and read in ONE worker-thread hop — every stat and the
            read stay off the event loop. Returns a tagged tuple: ``("ok", (bytes, name,
            immutable))``, ``("not_found", rel)``, or ``("no_index", target)``."""
            requested = (root / rel.lstrip("/")).resolve()
            target = (
                requested
                if requested.is_relative_to(root) and requested.is_file()
                else (root / "index.html" if fallback else None)
            )
            if target is None:
                return ("not_found", rel)
            if not target.is_file():
                # spa_fallback's own index.html is missing (public/ not built) -> a clear error
                # instead of a raw FileNotFoundError surfacing as an opaque 500
                return ("no_index", target)
            # anywhere under the assets dir counts — bundlers nest (assets/chunks/x-abc.js)
            immutable = assets_dirname in target.relative_to(root).parts[:-1]
            return ("ok", (target.read_bytes(), target.name, immutable))

        async def _serve(rel: str, fallback: bool) -> Any:
            from mimetypes import guess_type

            from anyio.to_thread import run_sync

            from arvel.http.exceptions import abort
            from arvel.http.response import Response
            from arvel.localization import trans

            tag, value = await run_sync(_locate, rel, fallback)
            if tag == "not_found":
                abort(404, trans("http.not_found"))
            if tag == "no_index":
                abort(500, f"public directory has no index.html — did you build it? ({value})")
            content, name, immutable = value
            content_type = guess_type(name)[0] or "application/octet-stream"
            cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
            return Response(
                content=content,
                status=200,
                headers={"content-type": content_type, "cache-control": cache},
            )

        if spa_fallback:
            # two thin handlers, not one shared function with an optional `path`: the root route's
            # template has no `{path}` placeholder, so a shared `path` param would be wrongly
            # inferred as a documented query parameter on that route
            async def _serve_root(request: Any) -> Any:
                return await _serve("", fallback=True)

            async def _serve_catchall(request: Any, path: str) -> Any:
                return await _serve(path, fallback=True)

            root_route = self.add(["GET"], path, _serve_root, "public.root")
            root_route.is_fallback = True
            catchall_route = self.add(
                ["GET"], path.rstrip("/") + "/{path:path}", _serve_catchall, "public"
            )
            catchall_route.is_fallback = True
        else:

            async def _serve_static(request: Any, path: str) -> Any:
                return await _serve(path, fallback=False)

            static_route = self.add(
                ["GET"], path.rstrip("/") + "/{path:path}", _serve_static, "public"
            )
            static_route.is_fallback = True
        return self

    def redirect(
        self, uri: str, destination: str, status: int = 302, name: str | None = None
    ) -> RouteDefinition:
        """A GET route that redirects to ``destination``."""
        from arvel.http.response import Response

        async def handler(request: Any) -> Response:
            return Response(status=status, headers={"Location": destination})

        return self.add(["GET"], uri, handler, name)

    def permanent_redirect(
        self, uri: str, destination: str, name: str | None = None
    ) -> RouteDefinition:
        """A 301 redirect route."""
        return self.redirect(uri, destination, status=301, name=name)

    def view(
        self, uri: str, view_name: str, data: dict[str, Any] | None = None, name: str | None = None
    ) -> RouteDefinition:
        """A GET route that renders a view with no controller."""
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
        secure: Sequence[str] | None = None,
        group: str | None = None,
        domain: str | None = None,
    ) -> Generator[Router]:
        """Open a route group. ``prefix``/``name`` extend the path and name prefixes;
        ``middleware`` adds middleware run for every route in the block; ``secure`` seeds the
        OpenAPI security schemes (e.g. ``["bearer"]``) every route in the block requires — the
        docs-side counterpart to ``middleware``, so a guarded subtree's enforcement and its
        documentation are declared together and can't drift; ``group`` assigns a named kernel
        middleware group (e.g. ``"web"``/``"api"``); ``domain`` (H1) constrains every route in
        the block to a host pattern (may contain a ``{param}`` segment, e.g.
        ``"{account}.example.com"`` — captured into the handler params like a path param).
        Nested groups compose (outer + inner middleware/security both apply) and restore on
        exit. A route's own ``.secure(...)`` still extends whatever the group seeded."""
        previous = (
            self._prefix,
            self._name_prefix,
            self._middleware,
            self._security,
            self._group,
            self._domain,
        )
        self._prefix += prefix
        self._name_prefix += name
        self._middleware = [*self._middleware, *(middleware or [])]
        self._security = [*self._security, *(secure or [])]
        if group is not None:
            self._group = group
        if domain is not None:
            self._domain = domain
        try:
            yield self
        finally:
            (
                self._prefix,
                self._name_prefix,
                self._middleware,
                self._security,
                self._group,
                self._domain,
            ) = previous

    def routes(self) -> list[RouteDefinition]:
        return list(self._routes)

    def url(self, name: str, **params: Any) -> str:
        """Generate a URL for a named route. Path placeholders
        ``{param}`` are filled from ``params``; any leftover params are appended as a
        URL-encoded query string. Raises ``ValueError`` if a required path param is
        missing, ``KeyError`` if no route has that name."""
        import re
        from urllib.parse import quote, urlencode

        for route in self._routes:
            if route.name == name:
                path = route.path
                query: dict[str, Any] = {}
                for key, value in params.items():
                    # match {key} or the route-key/converter form {key:conv}; encode the segment
                    placeholder = re.compile(r"\{" + re.escape(key) + r"(?::(?P<conv>[^}]*))?\}")
                    match = placeholder.search(path)
                    if match:
                        # a :path converter spans multiple segments, so keep its slashes
                        safe = "/" if match.group("conv") == "path" else ""
                        path = placeholder.sub(quote(str(value), safe=safe), path)
                    else:
                        query[key] = value
                unfilled = re.findall(r"\{([^}]+)\}", path)
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
        parity). Raises a clear error if neither is available."""
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
        """A tamper-evident URL for a named route.

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
        app key.

        Reconstructs the exact string ``signed_url`` signed by removing only the trailing
        ``signature=`` query segment — never by reserializing the query (DR-0047: that reorders
        and re-encodes, so the reconstructed base would no longer be byte-identical to what was
        signed, and every signature would fail).
        """
        import time
        from urllib.parse import urlsplit, urlunsplit

        from arvel.security import SignatureInvalid, Signer

        try:
            split = urlsplit(url)
        except ValueError:  # malformed URL (e.g. an invalid IPv6 host) — fail closed, never raise
            return False
        segments = split.query.split("&") if split.query else []
        if not segments or not segments[-1].startswith("signature="):
            return False
        token = segments[-1][len("signature=") :]  # raw — signed_url appends it unencoded
        remaining = segments[:-1]
        base = urlunsplit(
            (split.scheme, split.netloc, split.path, "&".join(remaining), split.fragment)
        )
        key = self._signing_key(key)
        try:
            if Signer(key).unsign(token) != base:
                return False
        except SignatureInvalid:
            return False
        marker = "expires="
        for segment in remaining:
            if segment.startswith(marker):
                try:
                    expires = int(segment[len(marker) :])
                except ValueError:
                    return False
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
                wheres=route.wheres,
                missing=route.missing_callback,
                without_middleware=route.excluded_middleware,
                domain=route.domain,
                scope_bindings=route.scoped,
                trashed_all=route.trashed_all,
                trashed_params=list(route.trashed_params),
                include_in_schema=route.include_in_schema,
            )
        for path, handler, name in self._websockets:
            kernel.add_websocket(path, handler, name)
        kernel.bindings.update(self._bindings)

    def current_route(self) -> RouteMatch | None:
        """The matched route for the active request (H4) — its name + resolved params, or
        ``None`` outside a request / before dispatch reaches binding resolution. Same object
        ``url().current_route()`` returns; exposed here too so the ``Route`` facade reads it
        directly (``Route.current_route()``)."""
        from arvel.http.request import current_route_match

        return current_route_match()

    def current_route_named(self, pattern: str) -> bool:
        """Whether the current route's name matches ``pattern`` (an ``fnmatch`` glob, e.g.
        ``"admin.*"``). ``False`` outside a request or on an unnamed route."""
        from arvel.http.request import current_route_match, route_matches_name

        return route_matches_name(current_route_match(), pattern)


def _absolute(path: str) -> str:
    """Join ``path`` onto ``config('app.url')`` — delegates to the one joiner (H16),
    ``arvel.support.helpers.app_url``. Kept as a name so routing's many internal callers
    (``_UrlGenerator``, ``route()``) are untouched."""
    from arvel.support.helpers import app_url

    return app_url(path)


class _UrlGenerator:
    """The ``url()`` global:
    ``url("/x")`` returns an absolute URL string; ``url()`` (no path) returns this generator so
    ``.current()``/``.full()``/``.previous()``/``.query()`` can chain off it — reads the active
    request via the same ``current_request`` contextvar the kernel already binds per-request."""

    def __call__(self, path: str | None = None) -> str | _UrlGenerator:
        return self if path is None else _absolute(path)

    def current(self) -> str:
        """The current request's absolute path (no query string). Raises ``RuntimeError`` outside
        an active request — there is no "current" URL to report."""
        return _absolute(self._request().path())

    def full(self) -> str:
        """The current request's absolute URL, query string included."""
        request = self._request()
        query = str(getattr(request.raw.url, "query", "") or "")
        return _absolute(request.path() + (f"?{query}" if query else ""))

    def previous(self, fallback: str = "/") -> str:
        """The ``Referer`` of the current request, or ``fallback`` when there's no active request
        or no Referer header (never raises — ``URL::previous`` always degrades)."""
        from arvel.http.request import current_request

        request = current_request.get(None)
        if request is None:
            return _absolute(fallback)
        referer = request.header("referer") or request.header("referrer")
        return referer or _absolute(fallback)

    def current_route(self) -> RouteMatch | None:
        """The matched route for the active request (H4) — name + resolved params. Unlike
        ``.current()``/``.full()`` this degrades to ``None`` outside a request instead of raising:
        "no current route" (no active request, or a path the router never finished matching) is a
        legitimate state, not a programming error."""
        from arvel.http.request import current_route_match

        return current_route_match()

    def current_route_named(self, pattern: str) -> bool:
        """Whether the current route's name matches ``pattern`` (an ``fnmatch`` glob). ``False``
        outside a request or on an unnamed route."""
        from arvel.http.request import current_route_match, route_matches_name

        return route_matches_name(current_route_match(), pattern)

    def query(self, path: str, params: dict[str, Any]) -> str:
        """``path`` with ``params`` appended as a URL-encoded query string."""
        from urllib.parse import urlencode

        qs = urlencode(params)
        return _absolute(f"{path}?{qs}" if qs else path)

    @staticmethod
    def _request() -> Any:
        from arvel.http.request import current_request

        request = current_request.get(None)
        if request is None:
            raise RuntimeError(
                "url().current()/.full() need an active request — called outside one."
            )
        return request


#: ``url("/x")`` → absolute string; ``url()`` → this generator, for ``.current()``/``.full()``/
#: ``.previous()``/``.query()``.
url = _UrlGenerator()


def route(name: str, *, absolute: bool = True, **params: Any) -> str:
    """The URL for a named route — absolute by default; pass
    ``absolute=False`` for the bare path (what ``Router.url`` itself returns)."""
    from arvel.kernel import app

    path: str = app("router").url(name, **params)
    return _absolute(path) if absolute else path


def to_route(name: str, **params: Any) -> Redirect:
    """``redirect().route(name, **params)`` sugar."""
    from arvel.http.redirect import redirect

    return redirect().route(name, **params)


def temporary_signed_route(name: str, expires_in: int, **params: Any) -> str:
    """A signed URL that expires ``expires_in`` seconds from now (``URL::temporarySignedRoute``) — sugar over ``Router.signed_url(expires=...)``."""
    import time

    from arvel.kernel import app

    return cast(
        "str", app("router").signed_url(name, expires=int(time.time()) + expires_in, **params)
    )


__all__ = [
    "Controller",
    "ControllerMiddleware",
    "RouteDefinition",
    "Router",
    "broadcast_websocket",
    "route",
    "temporary_signed_route",
    "to_route",
    "url",
    "verify_channel_auth",
]


def __getattr__(name: str) -> Any:
    # lazy — `verify_channel_auth`/`broadcast_websocket` live in routing's own submodules (no DAG
    # edge), re-exported here as the stable public surface a realtime transport imports (DR-0067),
    # so `import arvel.routing` doesn't eagerly pull in the broadcasting/auth wiring.
    if name == "verify_channel_auth":
        from arvel.routing.broadcasting_auth import verify_channel_auth

        return verify_channel_auth
    if name == "broadcast_websocket":
        from arvel.routing.broadcast_relay import broadcast_websocket

        return broadcast_websocket
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

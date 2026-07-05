"""arvel.views — server templating on **Jinja2** (mandated engine; the ``[view]`` extra).

``view("welcome", {...})`` builds a ``View`` (Blade-style dotted name → ``welcome.html``);
``ViewFactory`` wraps an async Jinja2 ``Environment`` (autoescape on) with framework
globals (``trans``/``trans_choice``). The frontend SPA toolchain is **decoupled** — Python
owns server templates + (P7.2) the Inertia protocol + the Vite manifest reader, not the JS
build. Jinja2 is imported lazily. Grounded in knowledge/port/09-views-templating.md.
"""

from __future__ import annotations

from typing import Any


async def _can(ability: str, *args: Any) -> bool:
    """Template auth helper (``{% if can('update', post) %}``): delegate to the bound Gate.
    Returns False when no gate/app is available, so templates degrade safely."""
    from arvel.kernel import app, has_application

    if not (has_application() and app().bound("gate")):
        return False
    allowed: bool = await app().make("gate").allows(ability, *args)
    return allowed


async def _cannot(ability: str, *args: Any) -> bool:
    """Inverse of :func:`_can` (``{% if cannot('update', post) %}``)."""
    return not await _can(ability, *args)


def _auth() -> Any:
    """Template ``auth()`` — the current authenticated user, or ``None``.
    ``{% if auth() %}Hi {{ auth().name }}{% endif %}``."""
    from arvel.support import current_user

    return current_user.get()


def _guest() -> bool:
    """Template ``guest()`` — ``True`` when no user is authenticated."""
    return _auth() is None


def _config(key: str, default: Any = None) -> Any:
    """Template ``config('app.name')`` helper — reads the bound config, or ``default``."""
    from arvel.kernel import app, has_application

    if not (has_application() and app().bound("config")):
        return default
    return app("config").get(key, default)


def _route(name: str, **params: Any) -> str:
    """Template ``route('posts.show', id=1)`` helper — a URL for a named route via the bound
    router; degrades to ``#`` when no app/router is available."""
    from arvel.kernel import app, has_application

    if not (has_application() and app().bound("router")):
        return "#"
    url: str = app("router").url(name, **params)
    return url


def _url(path: str = "") -> str:
    """Template ``url('/login')`` helper — joins ``config('app.url')`` with ``path``."""
    base = str(_config("app.url", "") or "").rstrip("/")
    suffix = ("/" + path.lstrip("/")) if path else ""
    return (base + suffix) if base else (suffix or "/")


def _csrf_token() -> str:
    """Template ``csrf_token()`` — the current session's CSRF token (seeded by the CSRF middleware),
    or "" when no request/session is present."""
    from typing import cast

    from arvel.http.request import current_request

    session = getattr(current_request.get(), "session", None)
    if not isinstance(session, dict):
        return ""
    token = cast("dict[str, Any]", session).get("_token", "")
    return token if isinstance(token, str) else ""


def _csrf_field() -> Any:
    """Template ``csrf_field()`` — a hidden ``_token`` input for HTML forms.
    The token is interpolated via ``Markup.format`` so it is escaped, not trusted verbatim."""
    from markupsafe import Markup

    return Markup('<input type="hidden" name="_token" value="{}">').format(_csrf_token())


def _method_field(method: str) -> Any:
    """Template ``method_field('PUT')`` — a hidden ``_method`` input so an HTML form can target a
    PUT/PATCH/DELETE route."""
    from markupsafe import Markup

    return Markup('<input type="hidden" name="_method" value="{}">').format(method.upper())


def _asset(path: str) -> str:
    """Template ``asset('css/app.css')`` helper — ``config('app.asset_url')`` (falling back to
    ``app.url``) joined with ``path``."""
    base = str(_config("app.asset_url", None) or _config("app.url", "") or "").rstrip("/")
    return f"{base}/{path.lstrip('/')}" if base else "/" + path.lstrip("/")


class View:
    """A resolved template + its data; rendered via the bound ``ViewFactory``."""

    def __init__(self, template: str, data: dict[str, Any] | None = None) -> None:
        self.template = template
        self.data = data or {}

    async def render(self) -> str:
        return await _factory().render(self)

    async def to_response(self) -> Any:
        from arvel.http import Response

        html = await self.render()
        return Response(html, headers={"content-type": "text/html; charset=utf-8"})


def view(name: str, data: dict[str, Any] | None = None) -> View:
    """Build a view from a Blade-style dotted name (``pages.home`` → ``pages/home.html``)."""
    return View(name.replace(".", "/") + ".html", data or {})


class ViewFactory:
    """An async Jinja2 environment with framework globals; resolves ``pkg::name`` later."""

    def __init__(self, paths: str | list[str] = "resources/views") -> None:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        self._main_loader: Any = FileSystemLoader(paths)
        self._namespaces: dict[str, Any] = {}  # name -> FileSystemLoader (pkg::view)
        self.env = Environment(
            loader=self._build_loader(),
            enable_async=True,
            autoescape=select_autoescape(default=True),
        )
        from arvel.localization import trans, trans_choice

        env_globals: dict[str, Any] = self.env.globals
        env_globals.update(
            trans=trans,
            trans_choice=trans_choice,
            can=_can,
            cannot=_cannot,
            config=_config,
            route=_route,
            url=_url,
            asset=_asset,
            csrf_token=_csrf_token,
            csrf_field=_csrf_field,
            method_field=_method_field,
            auth=_auth,
            guest=_guest,
        )

    def _build_loader(self) -> Any:
        from jinja2 import ChoiceLoader, PrefixLoader

        loaders: list[Any] = [self._main_loader]
        if self._namespaces:
            loaders.append(PrefixLoader(self._namespaces, delimiter="::"))
        return ChoiceLoader(loaders)

    def add_namespace(self, name: str, path: str | list[str]) -> ViewFactory:
        """Register a view namespace so ``name::template`` resolves under ``path``."""
        from jinja2 import FileSystemLoader

        self._namespaces[name] = FileSystemLoader(path)
        self.env.loader = self._build_loader()
        return self

    def share(self, **globals_: Any) -> None:
        """Register globals available to every template."""
        self.env.globals.update(globals_)

    async def render(self, view_obj: View) -> str:
        template = self.env.get_template(view_obj.template)
        rendered: str = await template.render_async(**view_obj.data)
        return rendered


def _factory() -> ViewFactory:
    from arvel.kernel import app, has_application

    if has_application() and app().bound("view"):
        factory: ViewFactory = app().make("view")
        return factory
    return ViewFactory()


__all__ = ["View", "ViewFactory", "view"]


# Wire pagination's page-link-bar renderer (views->pagination is a legal downward edge; the
# reverse isn't, DR-0026), so importing arvel.views makes paginator.links() render through Jinja.
import arvel.pagination as _pagination  # noqa: E402


async def _render_pagination(template: str, data: dict[str, object]) -> object:
    return await View(template, data).render()


_pagination.set_view_renderer(_render_pagination)

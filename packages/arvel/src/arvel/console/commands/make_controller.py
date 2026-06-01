"""``make:controller`` — generate an HTTP controller.

Arvel controllers subclass :class:`arvel.Controller`. The framework
supports two flavours:

- **Multi-action controllers** — implement ``index``, ``show``, ``store``,
  ``update``, ``destroy`` (and friends), each registered on a route via
  ``Route.get("/posts", controller=PostController, action="index")``.
- **Invokable controllers** — implement a single ``async __call__``,
  registered with ``Route.get("/dashboard", controller=Dashboard)``.

Action method parameters are resolved by FastAPI's DI: ``Request``,
typed path/query params, :class:`arvel.FormRequest` subclasses, and
``dep(MyService)`` for container-bound services.

The class name is completed automatically: ``make:controller Post`` and
``make:controller PostController`` both produce ``PostController``.

Flags:

``--resource``
    Generate the seven canonical CRUD method stubs (``index``, ``create``,
    ``store``, ``show``, ``edit``, ``update``, ``destroy``) — each
    raising ``NotImplementedError``. Pair with
    ``Route.resource("/posts", PostController)``.

``--api``
    Only valid with ``--resource``. Drops the two HTML-form methods
    (``create``, ``edit``). Mirrors ``Route.api_resource()``.

``--model`` / ``--model-name=Post``
    Generate the companion model (skipped if it already exists). Bare
    ``--model`` derives the name from the controller (``PostController`` →
    ``Post``); ``--model-name`` overrides it. Under ``--resource`` the
    controller also imports the model and types the member-method parameter
    as ``post: Post`` so [implicit model binding](../routing.md) resolves it.

``--observer`` / ``--policy`` / ``--requests``
    Generate the matching companions: ``PostObserver``, ``PostPolicy``,
    and the ``StorePostRequest`` / ``UpdatePostRequest`` pair.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option
from arvel.console.commands import _companions
from arvel.console.commands._base_make import BaseMakeCommand, validate_name
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — HTTP controller."""

from __future__ import annotations

from typing import Any

from arvel import Controller
from starlette.requests import Request


class {title}(Controller):
    """Resource controller. Wire actions on routes with ``action="index"``, etc."""

    async def index(self, request: Request) -> dict[str, Any]:
        return {{"items": []}}

    async def show(self, request: Request, id: int) -> dict[str, Any]:
        return {{"id": id}}

    async def store(self, request: Request) -> dict[str, Any]:
        return {{}}

    async def update(self, request: Request, id: int) -> dict[str, Any]:
        return {{"id": id}}

    async def destroy(self, request: Request, id: int) -> dict[str, Any]:
        return {{"id": id, "deleted": True}}
'''


# Resource template — one stub per action. Member methods accept a path
# parameter named ``id: int`` by default, or ``<snake_model>: <Model>``
# when ``--model`` is set. The body is always ``raise NotImplementedError``
# so the user knows what's still to do at a glance.
_RESOURCE_HEADER = '''"""{title} — resource controller."""

from __future__ import annotations

from typing import Any

from arvel import Controller
{model_import}

class {title}(Controller):
    """Bind with ``Route.resource(prefix, {title})`` (or ``Route.api_resource`` for JSON-only)."""
'''

_RESOURCE_METHOD_NO_PARAM = """
    async def {action}(self) -> dict[str, Any]:
        raise NotImplementedError
"""

_RESOURCE_METHOD_WITH_PARAM = """
    async def {action}(self, {param}: {param_type}) -> dict[str, Any]:
        raise NotImplementedError
"""


# Order matches Route.resource() so route:list output and the generated
# file scroll in the same direction.
_RESOURCE_ACTIONS: tuple[str, ...] = (
    "index",
    "create",
    "store",
    "show",
    "edit",
    "update",
    "destroy",
)

# Actions that take the resource member parameter (e.g. /posts/{post}).
_MEMBER_ACTIONS: frozenset[str] = frozenset({"show", "edit", "update", "destroy"})

# Actions that don't make sense on a JSON-only API.
_HTML_ONLY_ACTIONS: frozenset[str] = frozenset({"create", "edit"})


def _render_resource(name: str, *, api: bool, model: str | None) -> str:
    title = Str.pascal(name)
    if model is not None:
        model_snake = Str.snake(model)
        model_import = f"from app.models.{model_snake} import {model}\n"
        param = model_snake
        param_type = model
    else:
        model_import = ""
        param = "id"
        param_type = "int"

    actions = [a for a in _RESOURCE_ACTIONS if not (api and a in _HTML_ONLY_ACTIONS)]

    body = _RESOURCE_HEADER.format(title=title, model_import=model_import)
    for action in actions:
        if action in _MEMBER_ACTIONS:
            body += _RESOURCE_METHOD_WITH_PARAM.format(
                action=action, param=param, param_type=param_type
            )
        else:
            body += _RESOURCE_METHOD_NO_PARAM.format(action=action)
    return body


class MakeControllerCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:controller"
    help: ClassVar[str] = "Generate an HTTP controller (subclass of arvel.Controller)"
    _target_subdir: ClassVar[str] = "app/http/controllers"
    _suffix: ClassVar[str] = "Controller"

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            name: Annotated[str, _Argument(help="Controller name (e.g. Post or PostController)")],
            *,
            force: Annotated[
                bool,
                _Option("--force", help="Overwrite existing"),
            ] = False,
            resource: Annotated[
                bool,
                _Option("--resource", help="Generate the seven RESTful method stubs"),
            ] = False,
            api: Annotated[
                bool,
                _Option(
                    "--api",
                    help="Drop create()/edit() (HTML form methods). Requires --resource.",
                ),
            ] = False,
            model: Annotated[
                bool,
                _Option(
                    "--model",
                    help="Generate the model named after the controller (PostController → Post).",
                ),
            ] = False,
            model_name: Annotated[
                str | None,
                _Option("--model-name", help="Generate this model instead of the derived name."),
            ] = None,
            observer: Annotated[
                bool,
                _Option("--observer", help="Also generate the matching Observer."),
            ] = False,
            policy: Annotated[
                bool,
                _Option("--policy", help="Also generate the matching Policy."),
            ] = False,
            requests: Annotated[
                bool,
                _Option("--requests", help="Also generate Store/Update FormRequests."),
            ] = False,
        ) -> None:
            if api and not resource:
                typer.echo("arvel: --api requires --resource.", err=True)
                raise typer.Exit(2)

            model_root: str | None = None
            if model_name is not None:
                model_root = Str.pascal(model_name)
            elif model:
                model_root = cmd_self.root_name(name)

            code = cmd_self._generate(
                name, force=force, resource=resource, api=api, model_root=model_root
            )
            if code != 0:
                raise typer.Exit(code)

            root = cmd_self.root_name(name)
            if model_root is not None:
                code = _companions.model(model_root, force=force) or code
            if observer:
                code = _companions.observer(root, force=force) or code
            if policy:
                code = _companions.policy(root, force=force) or code
            if requests:
                code = _companions.form_requests(root, force=force) or code
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def generate(
        self,
        name: str,
        *,
        force: bool = False,
        exist_ok: bool = False,
        resource: bool = False,
        api: bool = False,
        model_root: str | None = None,
    ) -> int:
        """Public entry point used by companion orchestration (make:model --controller)."""
        return self._generate(
            name,
            force=force,
            exist_ok=exist_ok,
            resource=resource,
            api=api,
            model_root=model_root,
        )

    def _generate(
        self,
        name: str,
        *,
        force: bool = False,
        exist_ok: bool = False,
        resource: bool = False,
        api: bool = False,
        model_root: str | None = None,
    ) -> int:
        error = validate_name(name)
        if error is not None:
            typer.echo(f"arvel: {error}", err=True)
            return 2
        if model_root is not None:
            model_error = validate_name(model_root)
            if model_error is not None:
                typer.echo(f"arvel: {model_error}", err=True)
                return 2
        class_name = self.class_name(name)
        target = Path(self._target_subdir) / f"{Str.snake(class_name)}{self._extension}"
        if target.exists() and not force:
            if exist_ok:
                typer.echo(f"Exists: {target}")
                return 0
            typer.echo(f"arvel: {target} already exists. Pass --force to overwrite.", err=True)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        # The model is only imported/typed in resource controllers — the basic
        # template has no member methods to bind it to.
        typed_model = model_root if resource else None
        target.write_text(
            self._render_with_flags(class_name, resource=resource, api=api, model=typed_model)
        )
        typer.echo(f"Created: {target}")
        return 0

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))

    def _render_with_flags(
        self,
        name: str,
        *,
        resource: bool,
        api: bool,
        model: str | None,
    ) -> str:
        if resource:
            return _render_resource(name, api=api, model=model)
        return self._render(name)

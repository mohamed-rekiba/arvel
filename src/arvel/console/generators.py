"""``make:*`` code generators (Laravel ``artisan make:``).

Each generator is a single-command ``typer.Typer`` app (mounted lazily by
``LazyGroup``). They scaffold a typed stub into the app's ``app/<area>/`` package.
The pure file-writing core (:func:`generate`) takes a ``base`` path so it is unit
testable. Grounded in knowledge/port/13-console.md.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import typer

_CREATE_MIGRATION = (
    "from arvel.database import Migration\n\n\n"
    "class {cls}(Migration):\n"
    "    def up(self, schema):\n"
    "        def define(t):\n"
    "            t.id()\n"
    "            t.timestamps()\n\n"
    '        schema.create("{table}", define)\n\n'
    "    def down(self, schema):\n"
    '        schema.drop("{table}")\n'
)
_GENERIC_MIGRATION = (
    "from arvel.database import Migration\n\n\n"
    "class {cls}(Migration):\n"
    "    def up(self, schema):\n"
    "        ...\n\n"
    "    def down(self, schema):\n"
    "        ...\n"
)


def generate_migration(name: str, base: Path | None = None) -> Path:
    """Write a timestamped migration ``database/migrations/<ts>_<name>.py`` (Laravel
    ``make:migration``). A ``create_<table>_table`` name gets a create/drop stub; any other name
    (e.g. ``add_x_to_y``) gets a generic ``up``/``down`` stub (the schema builder has no alter op)."""
    from arvel.support import Str

    directory = (base or Path()) / "database" / "migrations"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y_%m_%d_%H%M%S")
    target = directory / f"{stamp}_{name}.py"
    if target.exists():
        message = f"migration {name!r} already exists at {target}"
        raise FileExistsError(message)
    cls = Str.studly(name)
    created = re.fullmatch(r"create_(\w+?)_table", name)
    if created:
        body = _CREATE_MIGRATION.format(cls=cls, table=created.group(1))
    else:
        body = _GENERIC_MIGRATION.format(cls=cls)
    target.write_text(body)
    return target


# kind -> (target folder, stub template keyed on {name})
_STUBS: dict[str, tuple[str, str]] = {
    "model": (
        "app/models",
        "from arvel import Model\n\n\nclass {name}(Model):\n    __fillable__: list[str] = []\n",
    ),
    "controller": (
        "app/controllers",
        "from typing import Any\n\n"
        "from arvel.routing import Controller\n\n\n"
        "class {name}(Controller):\n"
        "    async def index(self, request: Any) -> dict[str, Any]:\n"
        "        return {{}}\n",
    ),
    "middleware": (
        "app/middleware",
        "from typing import Any\n\n"
        "from arvel.http.middleware import Middleware\n\n\n"
        "class {name}(Middleware):\n"
        "    async def handle(self, request: Any, call_next: Any) -> Any:\n"
        "        return await call_next(request)\n",
    ),
    "request": (
        "app/requests",
        "from arvel.validation import FormRequest\n\n\nclass {name}(FormRequest):\n    pass\n",
    ),
    "job": (
        "app/jobs",
        "from typing import Any\n\n"
        "from arvel.queue import Job\n\n\n"
        "class {name}(Job):\n"
        "    async def handle(self) -> Any:\n"
        "        ...\n",
    ),
    "policy": (
        "app/policies",
        "from typing import Any\n\n\n"
        "class {name}:\n"
        "    async def view(self, user: Any, model: Any) -> bool:\n"
        "        return False\n\n"
        "    async def create(self, user: Any) -> bool:\n"
        "        return False\n",
    ),
    "notification": (
        "app/notifications",
        "from typing import Any\n\n"
        "from arvel.notifications import Notification\n\n\n"
        "class {name}(Notification):\n"
        "    def via(self, notifiable: Any) -> list[str]:\n"
        '        return ["mail"]\n\n'
        "    def to_array(self, notifiable: Any) -> dict[str, Any]:\n"
        "        return {{}}\n",
    ),
    "mail": (
        "app/mail",
        "from arvel.mail import Mailable\n\n\n"
        "class {name}(Mailable):\n"
        "    def build(self) -> Mailable:\n"
        '        return self.subject("{name}").html("<p>Hello</p>")\n',
    ),
    "rule": (
        "app/rules",
        "from typing import Any\n\n"
        "from arvel.validation import Rule\n\n\n"
        "class {name}(Rule):\n"
        '    message = "The :attribute is invalid."\n\n'
        "    async def passes(self, attribute: str, value: Any) -> bool:\n"
        "        return True\n",
    ),
    "seeder": (
        "database/seeders",
        "from arvel.database import Seeder\n\n\n"
        "class {name}(Seeder):\n"
        "    async def run(self) -> None:\n"
        "        ...\n",
    ),
    "factory": (
        "database/factories",
        "from typing import Any\n\n"
        "from arvel.database import Factory\n\n\n"
        "class {name}(Factory):\n"
        "    # model = ...  # the model this factory builds\n"
        "    def definition(self) -> dict[str, Any]:\n"
        "        return {{}}\n",
    ),
    "provider": (
        "app/providers",
        "from arvel.kernel import ServiceProvider\n\n\n"
        "class {name}(ServiceProvider):\n"
        "    def register(self) -> None:\n"
        "        ...\n\n"
        "    def boot(self) -> None:\n"
        "        ...\n",
    ),
    "command": (
        "app/commands",
        "from typing import Any\n\n"
        "from arvel.console import Command\n\n\n"
        "class {name}(Command):\n"
        '    signature = "app:command"  # the CLI invocation name (edit me)\n'
        '    description = ""\n\n'
        "    async def handle(self, *deps: Any) -> Any:\n"
        "        # register this command in a provider's commands() to wire it into the CLI\n"
        '        self.info("{name} ran")\n',
    ),
}


def generate(kind: str, name: str, base: Path | None = None) -> Path:
    """Write the ``kind`` stub for class ``name`` under ``base`` (defaults to cwd)."""
    from arvel.support import Str

    folder, template = _STUBS[kind]
    directory = (base or Path()) / folder
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").touch()
    target = directory / f"{Str.snake(name)}.py"
    if target.exists():
        message = f"{kind} {name!r} already exists at {target}"
        raise FileExistsError(message)
    target.write_text(template.format(name=name))
    return target


def _run(kind: str, name: str) -> None:
    try:
        target = generate(kind, name)
    except FileExistsError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(f"created {target}")


make_model_app = typer.Typer()


@make_model_app.command()
def make_model(name: str) -> None:
    """Generate an Active-Record model (app/models/)."""
    _run("model", name)


make_controller_app = typer.Typer()


@make_controller_app.command()
def make_controller(name: str) -> None:
    """Generate a controller (app/controllers/)."""
    _run("controller", name)


make_middleware_app = typer.Typer()


@make_middleware_app.command()
def make_middleware(name: str) -> None:
    """Generate a middleware (app/middleware/)."""
    _run("middleware", name)


make_request_app = typer.Typer()


@make_request_app.command()
def make_request(name: str) -> None:
    """Generate a FormRequest (app/requests/)."""
    _run("request", name)


make_job_app = typer.Typer()


@make_job_app.command()
def make_job(name: str) -> None:
    """Generate a queued job (app/jobs/)."""
    _run("job", name)


make_policy_app = typer.Typer()


@make_policy_app.command()
def make_policy(name: str) -> None:
    """Generate an authorization policy (app/policies/)."""
    _run("policy", name)


make_notification_app = typer.Typer()


@make_notification_app.command()
def make_notification(name: str) -> None:
    """Generate a notification (app/notifications/)."""
    _run("notification", name)


make_mail_app = typer.Typer()


@make_mail_app.command()
def make_mail(name: str) -> None:
    """Generate a mailable (app/mail/)."""
    _run("mail", name)


make_rule_app = typer.Typer()


@make_rule_app.command()
def make_rule(name: str) -> None:
    """Generate a validation rule (app/rules/)."""
    _run("rule", name)


make_seeder_app = typer.Typer()


@make_seeder_app.command()
def make_seeder(name: str) -> None:
    """Generate a database seeder (database/seeders/)."""
    _run("seeder", name)


make_factory_app = typer.Typer()


@make_factory_app.command()
def make_factory(name: str) -> None:
    """Generate a model factory (database/factories/)."""
    _run("factory", name)


make_provider_app = typer.Typer()


@make_provider_app.command()
def make_provider(name: str) -> None:
    """Generate a service provider (app/providers/)."""
    _run("provider", name)


make_command_app = typer.Typer()


@make_command_app.command()
def make_command(name: str) -> None:
    """Generate a console command (app/commands/) — register it in a provider's commands()."""
    _run("command", name)


make_migration_app = typer.Typer()


@make_migration_app.command()
def make_migration(name: str) -> None:
    """Generate a timestamped migration (database/migrations/), e.g. create_posts_table."""
    try:
        target = generate_migration(name)
    except FileExistsError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(f"created {target}")

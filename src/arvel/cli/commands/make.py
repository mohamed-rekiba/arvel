"""Code generators — module, model, controller, service, repository, and more."""

from __future__ import annotations

from pathlib import Path

import typer

from arvel.cli.templates.engine import render_template as _render_raw
from arvel.support.utils import pluralize as _pluralize
from arvel.support.utils import to_snake_case as _to_snake_case


def _render(template_name: str, context: dict[str, object]) -> str:
    """Render a stub template, respecting project-level stubs/ overrides."""
    return _render_raw(template_name, context, project_dir=Path.cwd())


make_app = typer.Typer(name="make", help="Code generation commands.")


def _write_file(filepath: Path, content: str) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    init = filepath.parent / "__init__.py"
    if not init.exists():
        init.write_text("")
    filepath.write_text(content)


def _module_base(module: str) -> Path:
    return Path.cwd() / "app" / "modules" / module


@make_app.command("module")
def module(
    name: str = typer.Argument(help="Module name (e.g., users)."),
) -> None:
    """Scaffold a full module with provider, routes, and subdirectories."""
    module_dir = _module_base(name)
    if module_dir.exists():
        typer.echo(f"Error: Module '{name}' already exists at {module_dir}")
        raise typer.Exit(code=1)

    subdirs = [
        "controllers",
        "models",
        "services",
        "repositories",
        "schemas",
        "jobs",
        "events",
        "listeners",
        "policies",
        "mail",
        "lang",
    ]
    for sub in subdirs:
        (module_dir / sub).mkdir(parents=True, exist_ok=True)
        (module_dir / sub / "__init__.py").write_text("")

    (module_dir / "__init__.py").write_text("")

    pascal = name.replace("_", " ").title().replace(" ", "")
    provider_content = _render(
        "provider.py.j2",
        {
            "module_name": name,
            "class_name": f"{pascal}ServiceProvider",
        },
    )
    (module_dir / "provider.py").write_text(provider_content)

    routes_content = _render(
        "routes.py.j2",
        {
            "module_name": name,
            "prefix": name,
        },
    )
    (module_dir / "routes.py").write_text(routes_content)

    typer.echo(f"Module created: {module_dir}")


@make_app.command("model")
def model(
    name: str = typer.Argument(help="Model class name (e.g., User)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
    with_migration: bool = typer.Option(False, "--migration", help="Also generate a migration."),
) -> None:
    """Generate a model file."""
    snake = _to_snake_case(name)
    table = _pluralize(snake)
    filepath = _module_base(module) / "models" / f"{snake}.py"

    content = _render(
        "model.py.j2",
        {
            "class_name": name,
            "table_name": table,
        },
    )
    _write_file(filepath, content)
    typer.echo(f"Model created: {filepath}")

    if with_migration:
        migration(name=f"create_{table}_table")


@make_app.command("controller")
def controller(
    name: str = typer.Argument(help="Controller class name (e.g., UserController)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
) -> None:
    """Generate a controller file."""
    snake = _to_snake_case(name)
    resource = name.replace("Controller", "")
    service_name = f"{resource}Service"
    filepath = _module_base(module) / "controllers" / f"{snake}.py"

    content = _render(
        "controller.py.j2",
        {
            "class_name": name,
            "resource": resource.lower(),
            "service_name": service_name,
            "service_file": _to_snake_case(service_name),
            "module_import": f"app.modules.{module}",
        },
    )
    _write_file(filepath, content)
    typer.echo(f"Controller created: {filepath}")


@make_app.command("service")
def service(
    name: str = typer.Argument(help="Service class name (e.g., UserService)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
) -> None:
    """Generate a service file."""
    snake = _to_snake_case(name)
    resource = name.replace("Service", "")
    repo_name = f"{resource}Repository"
    filepath = _module_base(module) / "services" / f"{snake}.py"

    content = _render(
        "service.py.j2",
        {
            "class_name": name,
            "resource": resource.lower(),
            "repo_name": repo_name,
            "repo_file": _to_snake_case(repo_name),
            "module_import": f"app.modules.{module}",
        },
    )
    _write_file(filepath, content)
    typer.echo(f"Service created: {filepath}")


@make_app.command("repository")
def repository(
    name: str = typer.Argument(help="Repository class name (e.g., UserRepository)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
) -> None:
    """Generate a repository file."""
    snake = _to_snake_case(name)
    model_name = name.replace("Repository", "")
    filepath = _module_base(module) / "repositories" / f"{snake}.py"

    content = _render(
        "repository.py.j2",
        {
            "class_name": name,
            "model_name": model_name,
            "model_file": _to_snake_case(model_name),
            "module_import": f"app.modules.{module}",
        },
    )
    _write_file(filepath, content)
    typer.echo(f"Repository created: {filepath}")


@make_app.command("job")
def job(
    name: str = typer.Argument(help="Job class name (e.g., SendWelcomeEmail)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
) -> None:
    """Generate a background job file."""
    snake = _to_snake_case(name)
    filepath = _module_base(module) / "jobs" / f"{snake}.py"

    content = _render("job.py.j2", {"class_name": name})
    _write_file(filepath, content)
    typer.echo(f"Job created: {filepath}")


@make_app.command("event")
def event(
    name: str = typer.Argument(help="Event class name (e.g., UserRegistered)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
) -> None:
    """Generate a domain event file."""
    snake = _to_snake_case(name)
    filepath = _module_base(module) / "events" / f"{snake}.py"

    content = _render(
        "event.py.j2",
        {
            "class_name": name,
            "description": f"{name} occurs",
        },
    )
    _write_file(filepath, content)
    typer.echo(f"Event created: {filepath}")


@make_app.command("listener")
def listener(
    name: str = typer.Argument(help="Listener class name (e.g., SendWelcomeEmailListener)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
    event_name: str = typer.Option("Event", "--event", help="Event class this handles."),
) -> None:
    """Generate an event listener file."""
    snake = _to_snake_case(name)
    filepath = _module_base(module) / "listeners" / f"{snake}.py"

    content = _render(
        "listener.py.j2",
        {
            "class_name": name,
            "event_name": event_name,
        },
    )
    _write_file(filepath, content)
    typer.echo(f"Listener created: {filepath}")


@make_app.command("policy")
def policy(
    name: str = typer.Argument(help="Policy class name (e.g., UserPolicy)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
) -> None:
    """Generate an authorization policy file."""
    snake = _to_snake_case(name)
    resource = name.replace("Policy", "").lower()
    filepath = _module_base(module) / "policies" / f"{snake}.py"

    content = _render(
        "policy.py.j2",
        {
            "class_name": name,
            "resource": resource,
        },
    )
    _write_file(filepath, content)
    typer.echo(f"Policy created: {filepath}")


@make_app.command("mail")
def mail(
    name: str = typer.Argument(help="Mail class name (e.g., WelcomeMail)."),
    module: str = typer.Option(..., "--module", "-m", help="Target module."),
) -> None:
    """Generate a mailable message file."""
    snake = _to_snake_case(name)
    filepath = _module_base(module) / "mail" / f"{snake}.py"

    content = _render(
        "mail.py.j2",
        {
            "class_name": name,
            "subject": name.replace("Mail", "").replace("Email", ""),
        },
    )
    _write_file(filepath, content)
    typer.echo(f"Mail created: {filepath}")


@make_app.command("migration")
def migration(
    name: str = typer.Argument(help="Migration name (e.g., create_users_table)."),
) -> None:
    """Generate a new migration file."""
    from arvel.data.config import DatabaseSettings
    from arvel.data.migrations import MigrationRunner

    settings = DatabaseSettings()
    migrations_dir = str(Path.cwd() / "database" / "migrations")
    runner = MigrationRunner(db_url=settings.url, migrations_dir=migrations_dir)
    path = runner.generate(name)
    typer.echo(f"Migration created: {path}")


@make_app.command("seeder")
def seeder(
    name: str = typer.Argument(help="Seeder class name (e.g., UserSeeder)."),
) -> None:
    """Generate a new seeder file."""
    seeders_dir = Path.cwd() / "database" / "seeders"
    seeders_dir.mkdir(parents=True, exist_ok=True)
    init_file = seeders_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")

    filename = _to_snake_case(name) + ".py"
    filepath = seeders_dir / filename

    filepath.write_text(
        f'"""Database seeder: {name}."""\n\n'
        f"from __future__ import annotations\n\n"
        f"from typing import TYPE_CHECKING\n\n"
        f"from arvel.data.seeder import Seeder\n\n"
        f"if TYPE_CHECKING:\n"
        f"    from arvel.data.transaction import Transaction\n\n\n"
        f"class {name}(Seeder):\n"
        f"    async def run(self, tx: Transaction) -> None:\n"
        f"        pass\n"
    )
    typer.echo(f"Seeder created: {filepath}")

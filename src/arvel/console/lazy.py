"""LazyGroup — the command tree that imports only the invoked command's module.

Registering N commands must not import N modules. Built-ins live in a static
``name -> "module:typer_app"`` manifest (plain strings, zero imports); the matched
command's module is imported and converted to a click command only when invoked.
This is how Typer and the T0 ``< 50 ms`` budget coexist (doc 13 §1). typer is
imported here, but ``arvel.console.lazy`` is only loaded on the CLI path.
"""

from __future__ import annotations

import importlib
from typing import Any, ClassVar

from typer.core import TyperGroup


class LazyGroup(TyperGroup):
    """A Typer group whose built-in commands are imported lazily, on demand."""

    commands_manifest: ClassVar[dict[str, str]] = {
        "about": "arvel.console.builtins:about_app",
        "extras": "arvel.console.builtins:extras_app",
        "new": "arvel.console.builtins:new_app",
        "serve": "arvel.console.builtins:serve_app",
        "down": "arvel.console.builtins:down_app",
        "up": "arvel.console.builtins:up_app",
        "make:model": "arvel.console.generators:make_model_app",
        "make:controller": "arvel.console.generators:make_controller_app",
        "make:middleware": "arvel.console.generators:make_middleware_app",
        "make:request": "arvel.console.generators:make_request_app",
        "make:job": "arvel.console.generators:make_job_app",
        "make:policy": "arvel.console.generators:make_policy_app",
        "make:notification": "arvel.console.generators:make_notification_app",
        "make:mail": "arvel.console.generators:make_mail_app",
        "make:rule": "arvel.console.generators:make_rule_app",
        "make:seeder": "arvel.console.generators:make_seeder_app",
        "make:factory": "arvel.console.generators:make_factory_app",
        "make:provider": "arvel.console.generators:make_provider_app",
        "make:command": "arvel.console.generators:make_command_app",
        "make:event": "arvel.console.generators:make_event_app",
        "make:listener": "arvel.console.generators:make_listener_app",
        "make:cast": "arvel.console.generators:make_cast_app",
        "make:observer": "arvel.console.generators:make_observer_app",
        "make:migration": "arvel.console.generators:make_migration_app",
        "db:seed": "arvel.console.seed:seed_app",
        "migrate": "arvel.console.migrate:migrate_app",
        "migrate:rollback": "arvel.console.migrate:rollback_app",
        "queue:work": "arvel.console.work:work_app",
        "package:discover": "arvel.console.discover:discover_app",
        "vendor:publish": "arvel.console.publish:vendor_publish_app",
        "route:list": "arvel.console.routes:route_list_app",
        "schedule:run": "arvel.console.schedule:schedule_app",
        "shell": "arvel.console.shell:shell_app",
        "tinker": "arvel.console.shell:shell_app",  # alias for shell, Laravel Tinker style
        "lang:list": "arvel.console.lang:lang_app",
    }

    # Commands that work *before* a project exists (installer mode). Everything else needs a
    # project (a bootstrap/app.py) and is hidden until then — doc 13 §One binary, two modes.
    installer_commands: ClassVar[set[str]] = {"new", "about", "extras"}

    def list_commands(self, ctx: Any) -> list[str]:
        from arvel.console.context import in_project

        names = set(super().list_commands(ctx)) | set(self.commands_manifest)
        if not in_project():  # installer mode → only the project-less commands are advertised
            return sorted(names & self.installer_commands)
        # in a project: also advertise app/provider command classes (CLI-3)
        from arvel.console.kernel import discover_app_commands

        names |= set(discover_app_commands())
        return sorted(names)

    def get_command(self, ctx: Any, cmd_name: str) -> Any:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        import typer

        target = self.commands_manifest.get(cmd_name)
        if target is not None:
            module_name, attr = target.split(":")
            sub_app = getattr(importlib.import_module(module_name), attr)
            return typer.main.get_command(sub_app)
        # app/provider command classes (CLI-3) + routes/console.py closures (Console.command)
        from arvel.console.closure import ClosureCommand
        from arvel.console.kernel import discover_app_commands, run_command_class

        descriptor = discover_app_commands().get(cmd_name)
        if descriptor is None:
            return None
        if isinstance(descriptor, ClosureCommand):
            try:
                return self._closure_command(cmd_name, descriptor)
            except Exception:
                # a malformed closure signature (e.g. a required arg after an optional one) must not
                # crash `--help` — degrade gracefully like a broken command class (kernel.py contract).
                from arvel.kernel.logging import LogManager

                LogManager().channel("console").warning(
                    "closure_command_invalid", command=cmd_name, exc_info=True
                )
                return None
        sub = typer.Typer()
        sub.command(name=cmd_name, help=(getattr(descriptor, "description", "") or None))(
            lambda: run_command_class(descriptor)
        )
        command = typer.main.get_command(sub)
        command.name = cmd_name  # display the registered name (not the wrapper fn's "<lambda>")
        return command

    @staticmethod
    def _closure_command(cmd_name: str, closure: Any) -> Any:
        """Build a command from a closure's Laravel-style signature — required/optional positional args
        + boolean ``--flags``. Built **through Typer** (a synthetic-signature callback) so it gets the
        same clean usage-error rendering as the built-in commands (a raw click.Command escapes Typer's
        error handling and surfaces a traceback on a missing argument). The callback dispatches the
        closure through the booted app (DI + the parsed tokens by name)."""
        import inspect

        import typer

        from arvel.console.closure import run_closure_command

        def run(**kwargs: Any) -> None:
            # drop omitted optional args (Typer yields None) so the handler's own default / container
            # DI applies instead of being overridden with None.
            run_closure_command(
                cmd_name, {key: value for key, value in kwargs.items() if value is not None}
            )

        parameters: list[inspect.Parameter] = []
        annotations: dict[str, Any] = {}
        seen_optional_positional = False
        for arg_name, is_option, optional in closure.arguments():
            if is_option:  # {--flag} → boolean option, default False
                parameters.append(
                    inspect.Parameter(arg_name, inspect.Parameter.KEYWORD_ONLY, default=False)
                )
                annotations[arg_name] = bool
            elif optional:  # {arg?} → optional POSITIONAL (None when omitted)
                seen_optional_positional = True
                # the default must be `typer.Argument(None)`, not a plain None: a plain default makes
                # Typer render the param as an `--option`, breaking `cmd value` for an optional arg.
                parameters.append(
                    inspect.Parameter(
                        arg_name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=typer.Argument(None),
                    )
                )
                annotations[arg_name] = str
            else:  # {arg} → required positional (Typer enforces; missing → usage error, exit 2)
                if seen_optional_positional:
                    raise ValueError(
                        f"closure command {cmd_name!r}: required argument {{{arg_name}}} cannot "
                        f"follow an optional one (an optional positional must come last)"
                    )
                parameters.append(
                    inspect.Parameter(arg_name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                )
                annotations[arg_name] = str
        run.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
        run.__annotations__ = annotations

        sub = typer.Typer(add_completion=False)  # no --install-completion noise on app commands
        sub.command(name=cmd_name)(run)
        command = typer.main.get_command(sub)
        command.name = cmd_name
        return command

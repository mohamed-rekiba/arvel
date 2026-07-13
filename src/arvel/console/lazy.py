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
        "make:enum": "arvel.console.generators:make_enum_app",
        "make:exception": "arvel.console.generators:make_exception_app",
        "make:test": "arvel.console.generators:make_test_app",
        "stub:publish": "arvel.console.generators:stub_publish_app",
        "db:seed": "arvel.console.seed:seed_app",
        "scout:import": "arvel.console.scout:scout_import_app",
        "scout:flush": "arvel.console.scout:scout_flush_app",
        "db:wipe": "arvel.console.migrate:wipe_app",
        "migrate": "arvel.console.migrate:migrate_app",
        "migrate:rollback": "arvel.console.migrate:rollback_app",
        "migrate:fresh": "arvel.console.migrate:fresh_app",
        "migrate:refresh": "arvel.console.migrate:refresh_app",
        "queue:work": "arvel.console.work:work_app",
        "queue:failed": "arvel.console.work:failed_app",
        "queue:retry": "arvel.console.work:retry_app",
        "cache:clear": "arvel.console.ops:cache_clear_app",
        "feature:list": "arvel.console.features:feature_list_app",
        "feature:purge": "arvel.console.features:feature_purge_app",
        "key:generate": "arvel.console.ops:key_generate_app",
        "storage:link": "arvel.console.ops:storage_link_app",
        "package:discover": "arvel.console.discover:discover_app",
        "vendor:publish": "arvel.console.publish:vendor_publish_app",
        "route:list": "arvel.console.routes:route_list_app",
        "openapi:export": "arvel.console.openapi:openapi_export_app",
        "schedule:run": "arvel.console.schedule:schedule_app",
        "schedule:work": "arvel.console.schedule:work_app",
        "auth:clear-resets": "arvel.console.auth_maintenance:auth_maintenance_app",
        "shell": "arvel.console.shell:shell_app",
        "tinker": "arvel.console.shell:shell_app",  # alias for shell, Tinker style
        "lang:list": "arvel.console.lang:lang_app",
    }

    # commands that work before a project exists; everything else is hidden until one does
    installer_commands: ClassVar[set[str]] = {"new", "about", "extras"}

    def list_commands(self, ctx: Any) -> list[str]:
        from arvel.console.context import in_project

        names = set(super().list_commands(ctx)) | set(self.commands_manifest)
        if not in_project():  # installer mode → only the project-less commands are advertised
            return sorted(names & self.installer_commands)
        # in a project: also advertise app/provider command classes
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
            command = typer.main.get_command(sub_app)
            # display the manifest key (`make:model`), not Typer's derived name (`make-model`);
            # display-only — invocation still routes through the manifest key
            command.name = cmd_name
            return command
        # app/provider command classes + routes/console.py closures (Console.command)
        from arvel.console.closure import ClosureCommand
        from arvel.console.kernel import discover_app_commands, run_command_class

        descriptor = discover_app_commands().get(cmd_name)
        if descriptor is None:
            return None
        if isinstance(descriptor, ClosureCommand):
            try:
                return self._closure_command(cmd_name, descriptor)
            except Exception:
                # a malformed closure signature must not crash --help; degrade like a broken command class
                from arvel.kernel.logging import LogManager

                LogManager().channel("console").warning(
                    "closure_command_invalid", command=cmd_name, exc_info=True
                )
                return None
        try:
            return self._command_class_command(cmd_name, descriptor, run_command_class)
        except Exception:
            from arvel.kernel.logging import LogManager

            LogManager().channel("console").warning(
                "command_class_signature_invalid", command=cmd_name, exc_info=True
            )
            return None

    @staticmethod
    def _command_class_command(cmd_name: str, descriptor: Any, run_command_class: Any) -> Any:
        """Build a command from an app/provider ``Command`` class's ``signature`` (same grammar as a
        closure — see ``console.closure``); the parsed CLI tokens are passed through to
        ``run_command_class`` so the kernel can stash them on the instance (``argument()``/``option()``)."""
        import inspect

        import typer

        from arvel.console.closure import parse_signature

        tokens = parse_signature(getattr(descriptor, "signature", "") or "")
        sub = typer.Typer()
        help_text = getattr(descriptor, "description", "") or None
        if tokens:

            def run(**kwargs: Any) -> None:
                run_command_class(
                    descriptor, **{key: value for key, value in kwargs.items() if value is not None}
                )

            parameters, annotations = _signature_typer_params(cmd_name, tokens)
            run.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
            run.__annotations__ = annotations
            sub.command(name=cmd_name, help=help_text)(run)
        else:
            sub.command(name=cmd_name, help=help_text)(lambda: run_command_class(descriptor))
        command = typer.main.get_command(sub)
        command.name = cmd_name  # display the registered name (not the wrapper fn's "<lambda>")
        return command

    @staticmethod
    def _closure_command(cmd_name: str, closure: Any) -> Any:
        """Build a command from a closure's signature — required/optional positional args
        + boolean ``--flags``. Built **through Typer** (a synthetic-signature callback) so it gets the
        same clean usage-error rendering as the built-in commands (a raw click.Command escapes Typer's
        error handling and surfaces a traceback on a missing argument). The callback dispatches the
        closure through the booted app (DI + the parsed tokens by name)."""
        import inspect

        import typer

        from arvel.console.closure import run_closure_command

        def run(**kwargs: Any) -> None:
            # drop omitted optional args so the handler's own default / container DI applies
            run_closure_command(
                cmd_name, {key: value for key, value in kwargs.items() if value is not None}
            )

        parameters, annotations = _signature_typer_params(cmd_name, closure.tokens())
        run.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
        run.__annotations__ = annotations

        sub = typer.Typer(add_completion=False)  # no --install-completion noise on app commands
        sub.command(name=cmd_name)(run)
        command = typer.main.get_command(sub)
        command.name = cmd_name
        return command


def _signature_typer_params(cmd_name: str, tokens: list[Any]) -> tuple[list[Any], dict[str, Any]]:
    """Build the ``inspect.Parameter`` list + annotations for a synthetic Typer callback from parsed
    signature tokens (shared by closure commands and app/provider ``Command`` classes — see
    ``console.closure`` for the grammar). A required positional after an optional one is rejected
    (an optional positional must come last, same rule enforces) — via the shared
    ``validate_positional_order``, so class commands fail with the same message closure
    registration raises."""
    import inspect

    import typer

    from arvel.support.command_signature import validate_positional_order

    validate_positional_order(tokens, cmd_name)
    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}
    for token in tokens:
        if token.is_option:
            decls = [f"--{token.name}", *([f"-{token.shortcut}"] if token.shortcut else [])]
            if token.variadic:  # {--opt=*}
                parameters.append(
                    inspect.Parameter(
                        token.name, inspect.Parameter.KEYWORD_ONLY, default=typer.Option([], *decls)
                    )
                )
                annotations[token.name] = list[str]
            elif token.takes_value:  # {--opt=}
                parameters.append(
                    inspect.Parameter(
                        token.name,
                        inspect.Parameter.KEYWORD_ONLY,
                        default=typer.Option(None, *decls),
                    )
                )
                annotations[token.name] = str | None
            elif token.shortcut:  # {--S|flag} boolean with a shortcut
                parameters.append(
                    inspect.Parameter(
                        token.name,
                        inspect.Parameter.KEYWORD_ONLY,
                        default=typer.Option(False, *decls),
                    )
                )
                annotations[token.name] = bool
            else:  # {--flag} → plain boolean option, default False (Typer's own --flag/--no-flag)
                parameters.append(
                    inspect.Parameter(token.name, inspect.Parameter.KEYWORD_ONLY, default=False)
                )
                annotations[token.name] = bool
        elif token.variadic:  # {arg*} → variadic POSITIONAL (a list; None when omitted)
            parameters.append(
                inspect.Parameter(
                    token.name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Argument(None),
                )
            )
            annotations[token.name] = list[str]
        elif token.optional:  # {arg?} / {arg=default} → optional POSITIONAL
            # a plain None default makes Typer render this as an --option instead of a positional arg
            parameters.append(
                inspect.Parameter(
                    token.name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Argument(token.default),
                )
            )
            annotations[token.name] = str
        else:  # {arg} → required positional (Typer enforces; missing → usage error, exit 2)
            parameters.append(
                inspect.Parameter(token.name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            )
            annotations[token.name] = str
    return parameters, annotations

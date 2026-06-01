"""Companion generation shared by ``make:model`` and ``make:controller``.

Each helper lazily imports the sibling generator (so the orchestrators can
import each other without a cycle) and delegates to its public ``generate``
method. The generator applies its own naming convention, so callers pass the
bare root (``Post``) and get the suffixed artifact (``PostController``,
``PostFactory``, …).

Companions are generated with ``exist_ok=True``: an artifact that already
exists is reported and skipped rather than aborting the whole command.
"""

from __future__ import annotations

from arvel.support.str import Str


def model(root: str, *, force: bool = False) -> int:
    from arvel.console.commands.make_model import MakeModelCommand

    return MakeModelCommand()._generate(root, force=force, exist_ok=True)


def migration(root: str) -> int:
    from arvel.console.commands.make_migration import MakeMigrationCommand

    name = f"Create{Str.pascal(Str.plural(Str.snake(root)))}Table"
    return MakeMigrationCommand().make(name)


def factory(root: str, *, force: bool = False) -> int:
    from arvel.console.commands.make_factory import MakeFactoryCommand

    return MakeFactoryCommand().generate(root, force=force, exist_ok=True)


def seeder(root: str, *, force: bool = False) -> int:
    from arvel.console.commands.make_seeder import MakeSeederCommand

    return MakeSeederCommand().generate(root, force=force, exist_ok=True)


def policy(root: str, *, force: bool = False) -> int:
    from arvel.console.commands.make_policy import MakePolicyCommand

    return MakePolicyCommand().generate(root, force=force, exist_ok=True)


def observer(root: str, *, force: bool = False) -> int:
    from arvel.console.commands.make_observer import MakeObserverCommand

    return MakeObserverCommand().generate(root, force=force, exist_ok=True)


def json_resource(root: str, *, force: bool = False) -> int:
    from arvel.console.commands.make_resource import MakeResourceCommand

    return MakeResourceCommand().generate(root, force=force, exist_ok=True)


def form_requests(root: str, *, force: bool = False) -> int:
    """Generate the ``Store{Root}Request`` + ``Update{Root}Request`` pair."""
    from arvel.console.commands.make_request import MakeRequestCommand

    cmd = MakeRequestCommand()
    store = cmd.generate(f"Store{Str.pascal(root)}", force=force, exist_ok=True)
    update = cmd.generate(f"Update{Str.pascal(root)}", force=force, exist_ok=True)
    return store or update


def feature_test(root: str, *, force: bool = False) -> int:
    from arvel.console.commands.make_test import MakeTestCommand

    return MakeTestCommand().generate(f"Test{Str.pascal(root)}", force=force, exist_ok=True)


def controller(
    root: str,
    *,
    force: bool = False,
    resource: bool = False,
    api: bool = False,
    model_root: str | None = None,
) -> int:
    from arvel.console.commands.make_controller import MakeControllerCommand

    return MakeControllerCommand()._generate(
        f"{Str.pascal(root)}Controller",
        force=force,
        exist_ok=True,
        resource=resource,
        api=api,
        model_root=model_root,
    )

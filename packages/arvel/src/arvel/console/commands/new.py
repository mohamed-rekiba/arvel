"""``arvel new <name>`` — scaffold a fresh Arvel project from the packaged skeleton.

The whole ``arvel`` framework CLI is shipped as a single binary; ``new`` is
the one command that runs *outside* a project (it has nothing to bootstrap
against yet). The entrypoint allows it explicitly — see
``arvel.console.entrypoint._OUTSIDE_PROJECT_ALLOWED_NAMES``.

Pipeline:

1. Validate the project name (allowlist regex + length cap).
2. Resolve the target directory (containment + non-empty refusal).
3. Render the packaged skeleton into a staging dir
 (token substitution, ``_dot_*`` → ``.*``, ``*.tmpl`` → ``*``).
4. Atomically promote staging → target (no half-installed projects).
5. Optionally run ``uv sync`` to populate ``.venv``.
6. Print next-steps. for the templating contract.
"""

import shutil

# Only invoked with the resolved `uv` binary and a static argv (`uv sync`).
import subprocess  # nosec B404
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._scaffold import (
    DEFAULT_KIT,
    InvalidProjectName,
    KitNotInstalledError,
    KitSpec,
    UnknownKitError,
    format_kit_listing,
    resolve_kit,
    resolve_target_directory,
    substitute,
    validate_project_name,
)
from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option

DEFAULT_PYTHON_VERSION = "3.14"

# Files copied byte-for-byte — skip token substitution to avoid corrupting
# binaries or files where ``{{ }}`` is legitimate text.
_NEVER_TEMPLATE_SUFFIXES: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".gif", ".ico"})

# Skip these directories under any kit source — they're build / cache
# artefacts that don't belong in a freshly-scaffolded project.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        ".venv",
        "venv",
        ".git",
        "dist",
        "build",
        ".vite",
    }
)


def _to_pascal_case(name: str) -> str:
    """``my-app`` → ``MyApp``; ``blog_orm`` → ``BlogOrm``."""
    parts = name.replace("-", "_").split("_")
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _final_name(name: str) -> str:
    """Resolve the skeleton's on-disk name to the user-visible filename.

    ``_dot_foo_bar`` → ``.foo.bar`` (the first ``_dot_`` is the dot prefix;
    subsequent underscores become dots). ``something.tmpl`` →
    ``something`` (drop the template suffix). Everything else is unchanged.
    """
    if name.startswith("_dot_"):
        rest = name[len("_dot_") :]
        return "." + rest.replace("_", ".")
    if name.endswith(".tmpl"):
        return name[: -len(".tmpl")]
    return name


def _should_skip(rel: Path) -> bool:
    """Return ``True`` when any path component is a build / cache dir."""
    return any(part in _SKIP_DIRS for part in rel.parts)


def _render_skeleton(
    skeleton_root: Path,
    target_root: Path,
    tokens: dict[str, str],
    *,
    apply_token_filenames: bool = True,
) -> None:
    """Copy every entry under ``skeleton_root`` into ``target_root``.

    Directory names copy verbatim, filenames go through ``_final_name``
    (when ``apply_token_filenames`` is true — the bundled ``api`` skeleton
    uses ``_dot_*`` / ``*.tmpl`` conventions), text files get tokens
    substituted, and binaries copy as-is.
    """
    for source in skeleton_root.rglob("*"):
        rel = source.relative_to(skeleton_root)
        if _should_skip(rel):
            continue
        rel_parts = list(rel.parts)
        if apply_token_filenames:
            rel_parts[-1] = _final_name(rel_parts[-1])
        destination = target_root.joinpath(*rel_parts)
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in _NEVER_TEMPLATE_SUFFIXES:
            shutil.copyfile(source, destination)
            continue
        try:
            content = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            shutil.copyfile(source, destination)
            continue
        rendered = substitute(content, tokens) if apply_token_filenames else content
        destination.write_text(rendered, encoding="utf-8")


def _print_next_steps(name: str, *, no_install: bool, kit: str = DEFAULT_KIT) -> None:
    typer.echo("")
    typer.echo(f"Created {name}/ from the {kit!r} kit.")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  cd {name}")
    if no_install:
        typer.echo("  uv sync")
    typer.echo("  uv run arvel serve")
    typer.echo("")


def _validate_name(name: str) -> str:
    try:
        return validate_project_name(name)
    except InvalidProjectName as exc:
        typer.echo(f"arvel: invalid project name: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _resolve_kit_or_exit(kit: str) -> KitSpec:
    try:
        kit_spec = resolve_kit(kit)
    except UnknownKitError as exc:
        typer.echo(f"arvel: {exc}", err=True)
        typer.echo(format_kit_listing(), err=True)
        raise typer.Exit(code=2) from exc
    return kit_spec


def _resolve_kit_root_or_exit(kit_spec: KitSpec) -> Path:
    try:
        return kit_spec.root()
    except KitNotInstalledError as exc:
        typer.echo(
            f"arvel: kit {kit_spec.name!r} requires the {exc.package!r} package; "
            f"install it with `pip install {exc.package}` (or "
            f"`uv add {exc.package}`) and try again.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except FileNotFoundError as exc:
        typer.echo(f"arvel: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _resolve_target_or_exit(validated: str, cwd: Path) -> Path:
    try:
        return resolve_target_directory(validated, cwd)
    except InvalidProjectName as exc:
        typer.echo(f"arvel: invalid target: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except FileExistsError as exc:
        typer.echo(f"arvel: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@dataclass(frozen=True)
class _StageOptions:
    cwd: Path
    target: Path
    validated: str
    tokens: dict[str, str]
    apply_template: bool


def _stage_and_promote(kit_root: Path, opts: _StageOptions) -> None:
    """Render kit into a temp dir then atomically promote into ``opts.target``."""
    staging_parent = tempfile.mkdtemp(prefix=f".arvel-new-{opts.validated}-", dir=str(opts.cwd))
    staging = Path(staging_parent) / opts.validated
    try:
        _render_skeleton(kit_root, staging, opts.tokens, apply_token_filenames=opts.apply_template)
        if opts.target.exists():
            shutil.copytree(staging, opts.target, dirs_exist_ok=True)
        else:
            opts.target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging), str(opts.target))
    finally:
        if Path(staging_parent).exists():
            shutil.rmtree(staging_parent, ignore_errors=True)


def _run_uv_sync(target: Path) -> None:
    uv_bin = shutil.which("uv")
    if uv_bin is None:
        typer.echo(
            "arvel: 'uv' not found on PATH — skipping `uv sync`. Run it manually.",
            err=True,
        )
        return
    try:
        # Static allowlist: resolved `uv` binary + literal "sync"; no user-controlled tokens.
        subprocess.run(  # noqa: S603  # nosec B603
            [uv_bin, "sync"],
            cwd=target,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        typer.echo(f"arvel: `uv sync` failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _scaffold(
    name: str,
    *,
    no_install: bool,
    python: str | None,
    kit: str = DEFAULT_KIT,
) -> None:
    """Inner driver shared by the Typer callback and tests."""
    validated = _validate_name(name)
    kit_spec = _resolve_kit_or_exit(kit)
    kit_root = _resolve_kit_root_or_exit(kit_spec)

    cwd = Path.cwd()
    target = _resolve_target_or_exit(validated, cwd)

    tokens: dict[str, str] = {
        "project_name": validated,
        "project_name_pascal": _to_pascal_case(validated),
        "python_version": python or DEFAULT_PYTHON_VERSION,
    }

    # Only the default ``api`` kit uses ``_dot_*`` / ``*.tmpl`` / ``{{token}}``
    # filename conventions. External kits may ship pre-rendered trees.
    apply_template = kit_spec.name == DEFAULT_KIT
    _stage_and_promote(
        kit_root,
        _StageOptions(
            cwd=cwd,
            target=target,
            validated=validated,
            tokens=tokens,
            apply_template=apply_template,
        ),
    )

    if not no_install:
        _run_uv_sync(target)

    _print_next_steps(validated, no_install=no_install, kit=kit_spec.name)


def _new_callback(
    project_name: Annotated[
        str,
        _Argument(
            metavar="NAME",
            help="Project name. Must match ^[a-z][a-z0-9_-]*$ (max 64 chars).",
        ),
    ],
    *,
    no_install: Annotated[
        bool,
        _Option("--no-install", help="Skip `uv sync` after generation."),
    ] = False,
    python: Annotated[
        str | None,
        _Option("--python", help="Python version constraint (e.g. '3.14')."),
    ] = None,
    kit: Annotated[
        str,
        _Option(
            "--kit",
            help=(
                "Starter kit to scaffold from. Default: 'api'. "
                "Run `arvel new --help` to see installed kits."
            ),
        ),
    ] = DEFAULT_KIT,
) -> None:
    _scaffold(project_name, no_install=no_install, python=python, kit=kit)


class NewCommand(Command):
    """``arvel new <name>`` — scaffold a project from the packaged skeleton."""

    name: ClassVar[str] = "new"
    help: ClassVar[str] = "Scaffold a new Arvel project from the packaged skeleton"

    def register(self, app: typer.Typer) -> None:
        # Defined at module level so Python 3.14+ annotation inspection works
        # correctly; Typer's get_type_hints() fails for closures in 3.14.5+.
        app.command(name=self.name, help=self.help)(_new_callback)

    def handle(self, ctx: Context) -> int:
        # All work happens in the Typer callback registered above. The
        # ``handle`` path is unused but required by the abstract base.
        raise NotImplementedError

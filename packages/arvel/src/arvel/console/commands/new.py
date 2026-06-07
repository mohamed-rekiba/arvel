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

import re
import shutil

# Only invoked with the resolved `uv` binary and a static argv (`uv sync …`).
import subprocess  # nosec B404
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._scaffold import (
    DEFAULT_KIT,
    InvalidProjectName,
    KitSpec,
    KitUnavailableError,
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


def _print_next_steps(
    name: str,
    *,
    no_install: bool,
    kit_spec: KitSpec,
    sync_args: Sequence[str] = ("sync",),
) -> None:
    typer.echo("")
    typer.echo(f"Created {name}/ from the {kit_spec.name!r} kit.")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  cd {name}")
    if no_install:
        sync_cmd = "uv " + " ".join(sync_args)
        subdir = kit_spec.python_project_subdir
        typer.echo(f"  (cd {subdir} && {sync_cmd})" if subdir else f"  {sync_cmd}")
    for command in kit_spec.next_step_commands:
        typer.echo(f"  {command}")
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
    except KitUnavailableError as exc:
        typer.echo(f"arvel: kit {exc.name!r} is unavailable: {exc.hint}", err=True)
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


def _uv_sync_args(kit: str) -> tuple[str, ...]:
    """The api skeleton has no extras; the e-commerce kit pulls many + a dev group."""
    if kit == DEFAULT_KIT:
        return ("sync",)
    return ("sync", "--all-extras", "--dev")


def _run_uv_sync(target: Path, args: Sequence[str]) -> None:
    uv_bin = shutil.which("uv")
    command = "uv " + " ".join(args)
    if uv_bin is None:
        typer.echo(
            f"arvel: 'uv' not found on PATH — skipping `{command}`. Run it manually.",
            err=True,
        )
        return
    try:
        # Static allowlist: resolved `uv` binary + literal sync flags; no user-controlled tokens.
        subprocess.run(  # noqa: S603  # nosec B603
            [uv_bin, *args],
            cwd=target,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        typer.echo(f"arvel: `{command}` failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


# uv workspace plumbing that only works inside the Arvel monorepo. The kit
# ships these so its own tests resolve `arvel` locally; in a scaffolded project
# they make `uv sync` fail ("references a workspace … but is not a member").
_MONOREPO_TOML_TABLES: tuple[str, ...] = ("tool.uv.sources", "tool.uv")


def _strip_toml_table(text: str, header: str) -> str:
    """Drop a whole ``[header]`` table — its body runs to the next table or EOF."""
    pattern = rf"(?ms)^\[{re.escape(header)}\][^\n]*\n.*?(?=^\[|\Z)"
    return re.sub(pattern, "", text)


def _localize_scaffolded_pyproject(project_root: Path, project: str, kit: str) -> None:
    """Turn the kit's copied pyproject into a standalone project's pyproject.

    The api skeleton substitutes ``{{project_name}}`` tokens; the e-commerce kit
    is copied verbatim, so its monorepo identity is rewritten here — the project
    name, and the workspace-only ``[tool.uv]`` / ``[tool.uv.sources]`` tables
    that otherwise break ``uv sync`` outside the Arvel checkout. ``project`` is
    validated against PROJECT_NAME_REGEX, so it's safe to inline. ``project_root``
    is the dir holding the pyproject (``backend/`` for the e-commerce kit).
    """
    if kit == DEFAULT_KIT:
        return
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return
    original = pyproject.read_text(encoding="utf-8")
    text = re.sub(
        r'(?m)^name\s*=\s*"arvel-ecommerce-kit"',
        f'name = "{project}"',
        original,
        count=1,
    )
    for header in _MONOREPO_TOML_TABLES:
        text = _strip_toml_table(text, header)
    text = text.rstrip() + "\n"
    if text != original:
        pyproject.write_text(text, encoding="utf-8")


# The kit's docker-compose.yml is authored for the monorepo: it bind-mounts the
# repo root (`../..`), works out of `kits/arvel-ecommerce-kit/backend`, and syncs
# the whole uv workspace (`--all-packages`) so `arvel` resolves from source. A
# scaffolded project has none of that — `pyproject.toml` and `backend/` sit at the
# project root and `arvel` comes from PyPI. Rewrite the monorepo paths so
# `docker compose up` works in the generated project.
_COMPOSE_MONOREPO_REWRITES: tuple[tuple[str, str], ...] = (
    ("/workspace/kits/arvel-ecommerce-kit/backend", "/workspace/backend"),
    ("cd kits/arvel-ecommerce-kit/backend", "cd backend"),
    ("../..:/workspace", ".:/workspace"),
    ("uv sync --frozen --all-packages", "uv sync --frozen"),
)


def _localize_scaffolded_compose(target: Path, kit: str) -> None:
    """Rewrite the kit's monorepo docker-compose.yml for the standalone project."""
    if kit == DEFAULT_KIT:
        return
    compose = target / "docker-compose.yml"
    if not compose.is_file():
        return
    original = compose.read_text(encoding="utf-8")
    text = original
    for monorepo, standalone in _COMPOSE_MONOREPO_REWRITES:
        text = text.replace(monorepo, standalone)
    if text != original:
        compose.write_text(text, encoding="utf-8")


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

    # The e-commerce kit nests its Python project under backend/; the api kit is flat.
    python_project_dir = target / kit_spec.python_project_subdir

    _localize_scaffolded_pyproject(python_project_dir, validated, kit_spec.name)
    _localize_scaffolded_compose(target, kit_spec.name)

    sync_args = _uv_sync_args(kit_spec.name)
    if not no_install:
        _run_uv_sync(python_project_dir, sync_args)

    _print_next_steps(validated, no_install=no_install, kit_spec=kit_spec, sync_args=sync_args)


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

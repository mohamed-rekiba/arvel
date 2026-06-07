"""The e-commerce kit's post-render ``finalize`` step.

The kit is authored *inside* the Arvel monorepo: its ``pyproject.toml`` carries
the uv-workspace plumbing and its ``docker-compose.yml`` bind-mounts the repo
root and syncs the whole workspace. A scaffolded standalone project has none of
that — the only ``pyproject.toml`` sits in ``backend/`` and ``arvel`` comes from
PyPI. Turning the monorepo layout into a standalone one is the kit's own
concern, so it lives here and is wired onto the kit via ``KitSpec.finalize``
instead of being special-cased inside the generic ``arvel new`` pipeline.
"""

from __future__ import annotations

import re

from arvel.console._scaffold.context import ScaffoldContext

# uv-workspace plumbing that only resolves inside the Arvel checkout. The kit
# ships these so its own tests import `arvel` from source; in a scaffolded
# project they make `uv sync` fail ("references a workspace … but is not a
# member"), so they're stripped.
_MONOREPO_TOML_TABLES: tuple[str, ...] = ("tool.uv.sources", "tool.uv")

# Monorepo → standalone rewrites for docker-compose.yml. In the monorepo
# `/workspace` is the repo root (holds the workspace pyproject, synced with
# `--all-packages`) and the app runs from `kits/arvel-ecommerce-kit/backend`.
# Standalone, the bind-mount is the project root and the only pyproject is in
# `backend/`, so `uv sync` must run from `/workspace/backend` — otherwise it
# errors "No pyproject.toml found". The trailing `cd /workspace/backend` is then
# a harmless no-op, which keeps every entry an independent string swap.
_COMPOSE_MONOREPO_REWRITES: tuple[tuple[str, str], ...] = (
    ("/workspace/kits/arvel-ecommerce-kit/backend", "/workspace/backend"),
    ("cd /workspace &&", "cd /workspace/backend &&"),
    ("cd kits/arvel-ecommerce-kit/backend", "cd /workspace/backend"),
    ("../..:/workspace", ".:/workspace"),
    ("uv sync --frozen --all-packages", "uv sync --frozen"),
)


def _strip_toml_table(text: str, header: str) -> str:
    """Drop a whole ``[header]`` table — its body runs to the next table or EOF."""
    pattern = rf"(?ms)^\[{re.escape(header)}\][^\n]*\n.*?(?=^\[|\Z)"
    return re.sub(pattern, "", text)


def _localize_pyproject(ctx: ScaffoldContext) -> None:
    """Rewrite the kit's monorepo pyproject into a standalone project's."""
    pyproject = ctx.python_project_dir / "pyproject.toml"
    if not pyproject.is_file():
        return
    original = pyproject.read_text(encoding="utf-8")
    text = re.sub(
        r'(?m)^name\s*=\s*"arvel-ecommerce-kit"',
        f'name = "{ctx.project_name}"',
        original,
        count=1,
    )
    for header in _MONOREPO_TOML_TABLES:
        text = _strip_toml_table(text, header)
    text = text.rstrip() + "\n"
    if text != original:
        pyproject.write_text(text, encoding="utf-8")


def _localize_compose(ctx: ScaffoldContext) -> None:
    """Rewrite the kit's monorepo docker-compose.yml for the standalone project."""
    compose = ctx.target / "docker-compose.yml"
    if not compose.is_file():
        return
    original = compose.read_text(encoding="utf-8")
    text = original
    for monorepo, standalone in _COMPOSE_MONOREPO_REWRITES:
        text = text.replace(monorepo, standalone)
    if text != original:
        compose.write_text(text, encoding="utf-8")


def finalize_ecommerce_project(ctx: ScaffoldContext) -> None:
    """Strip the kit's monorepo identity so the standalone project stands alone."""
    _localize_pyproject(ctx)
    _localize_compose(ctx)

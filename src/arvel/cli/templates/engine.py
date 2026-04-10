"""Template engine — Jinja2 loader with user stubs fallback.

Looks for templates in the user's ``stubs/`` directory first, then
falls back to the built-in templates shipped with the framework.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _builtin_stubs_dir() -> Path:
    return Path(__file__).parent / "stubs"


def create_environment(project_dir: Path | None = None) -> Environment:
    """Build a Jinja2 Environment with user stubs taking precedence over built-in."""
    search_paths: list[str] = []

    if project_dir is not None:
        user_stubs = project_dir / "stubs"
        if user_stubs.is_dir():
            search_paths.append(str(user_stubs))

    search_paths.append(str(_builtin_stubs_dir()))

    return Environment(
        loader=FileSystemLoader(search_paths),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(
    template_name: str,
    context: dict[str, object],
    *,
    project_dir: Path | None = None,
) -> str:
    """Render a template by name with the given context."""
    env = create_environment(project_dir)
    template = env.get_template(template_name)
    return template.render(**context)


def builtin_template_names() -> list[str]:
    """Return sorted list of all built-in template filenames."""
    stubs_dir = _builtin_stubs_dir()
    return sorted(f.name for f in stubs_dir.iterdir() if f.suffix == ".j2")

"""View / template rendering — Jinja2 backend.

Templates are loaded from directories listed in ``config/view.py`` under
the module-level ``paths`` attribute. Auto-escaping is enabled for any
template whose name ends in an HTML-ish suffix (``.html``, ``.htm``,
``.xml``, ``.html.j2``, ``.html.jinja``) and disabled for everything
else, so plain-text email bodies and JSON fragments are not silently
HTML-escaped while sharing a render context with HTML siblings.

If no ``config/view.py`` is registered, ``render_template`` falls back to
the canonical ``resources/views`` directory under the current working
directory. That keeps quick scripts and the framework's own tests working
without explicit config setup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, FileSystemBytecodeCache, FileSystemLoader, select_autoescape

# Cached per-process Environment. Most apps register their config once at
# bootstrap and never change paths after that — caching the Environment
# avoids rebuilding the loader on every render.
_environment_cache: Environment | None = None

# Default bytecode cache directory (mirrors Laravel's bootstrap/views).
_BYTECODE_CACHE_DIR = Path("bootstrap") / "views"


def _resolve_paths() -> list[str]:
    """Resolve template search paths from ``config/view.py``.

    Returns a list of absolute directory paths (Jinja2's
    ``FileSystemLoader`` accepts strings, so we resolve early to surface
    relative-path mistakes at config time rather than at first render).
    """
    from arvel.config import lookup  # noqa: PLC0415
    from arvel.config._lookup_registry import ConfigKeyError  # noqa: PLC0415

    try:
        raw: object = lookup("view.paths")
    except ConfigKeyError:
        return [str(Path("resources/views").resolve())]

    if not isinstance(raw, list):
        raise TypeError(
            f"config/view.py: `paths` must be a list of directories, got {type(raw).__name__}",
        )

    # ``cast`` to a typed sequence so the loop variable has a known static
    # type — the runtime contents are validated below.
    entries = cast("list[object]", raw)

    resolved: list[str] = []
    for entry in entries:
        if not isinstance(entry, str | Path):
            raise TypeError(
                "config/view.py: each entry in `paths` must be a str or Path, "
                f"got {type(entry).__name__}",
            )
        resolved.append(str(Path(entry).resolve()))
    return resolved


def _build_environment(*, bytecode_cache_dir: Path | None = None) -> Environment:
    kwargs: dict[str, Any] = {}
    if bytecode_cache_dir is not None and bytecode_cache_dir.is_dir():
        kwargs["bytecode_cache"] = FileSystemBytecodeCache(str(bytecode_cache_dir))
    return Environment(
        loader=FileSystemLoader(_resolve_paths()),
        autoescape=select_autoescape(
            enabled_extensions=("html", "htm", "xml", "html.j2", "html.jinja"),
            default_for_string=False,
        ),
        trim_blocks=True,
        lstrip_blocks=True,
        # Preserve trailing newlines so plain-text email bodies render exactly
        # as authored. Jinja2's default strips a final ``\n`` which surprises
        # template authors and can mangle the wire format of plain-text mail.
        keep_trailing_newline=True,
        **kwargs,
    )


def render_template(template: str, data: dict[str, Any]) -> str:
    """Render a Jinja2 template by name with the given context data.

    Resolves ``template`` against the directories listed in
    ``config/view.py:paths`` (or ``resources/views`` if none configured).
    Returns the rendered string. Raises Jinja2's ``TemplateNotFound`` when
    the template cannot be located in any of the search paths.
    """
    global _environment_cache  # noqa: PLW0603 — module-level cache; reset_cache() is the documented escape hatch
    if _environment_cache is None:
        _environment_cache = _build_environment(
            bytecode_cache_dir=_BYTECODE_CACHE_DIR if _BYTECODE_CACHE_DIR.is_dir() else None
        )
    return _environment_cache.get_template(template).render(**data)


def warm_bytecode_cache() -> int:
    """Compile all templates into the bytecode cache and return the count.

    Creates ``bootstrap/views/`` if needed, then loads every template in
    the configured search paths so Jinja2 writes its ``.cache`` files.
    Returns the number of templates compiled.
    """
    _BYTECODE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    env = _build_environment(bytecode_cache_dir=_BYTECODE_CACHE_DIR)
    names = env.list_templates()
    for name in names:
        env.get_template(name)
    # Rebuild the runtime environment to pick up the cache.
    global _environment_cache  # noqa: PLW0603
    _environment_cache = None
    return len(names)


def clear_bytecode_cache() -> None:
    """Delete all compiled bytecode files from ``bootstrap/views/``."""
    if not _BYTECODE_CACHE_DIR.exists():
        return
    for p in _BYTECODE_CACHE_DIR.iterdir():
        if p.is_file():
            p.unlink(missing_ok=True)


def reset_cache() -> None:
    """Drop the cached Jinja2 Environment.

    Tests that swap config registries between cases must call this before
    rendering, so the new ``view.paths`` take effect on the next render.
    """
    global _environment_cache  # noqa: PLW0603
    _environment_cache = None


__all__ = ["clear_bytecode_cache", "render_template", "reset_cache", "warm_bytecode_cache"]

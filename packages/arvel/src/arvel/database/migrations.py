"""Migration runtime + reversibility checker."""

from __future__ import annotations

import ast
import inspect
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from arvel.database.exceptions import MigrationNotReversibleError
from arvel.support.str import Str

# ── migration name inference ────────────────────────────────────────────────

_VERB_PREFIXES: tuple[str, ...] = (
    "create_",
    "add_",
    "drop_",
    "alter_",
    "update_",
    "modify_",
)
_EXTENSION_PREFIXES: tuple[str, ...] = ("install_", "uninstall_", *_VERB_PREFIXES)


def extract_table_name(name: str) -> str:
    """Derive the table name from a migration class name.

    ``CreateUsersTable`` → ``users``, ``CreateCategoryTable`` → ``categories``.
    """
    snake = Str.snake(name).removesuffix("_table")
    for prefix in _VERB_PREFIXES:
        if snake.startswith(prefix):
            snake = snake[len(prefix) :]
            break
    return Str.plural(snake)


def extract_view_name(name: str) -> str:
    """Derive a view name from a migration class name.

    ``CreateActiveUsersView`` → ``active_users``. No pluralisation — view
    names reflect query semantics, not a collection convention.
    """
    snake = Str.snake(name).removesuffix("_view")
    for prefix in _VERB_PREFIXES:
        if snake.startswith(prefix):
            snake = snake[len(prefix) :]
            break
    return snake


def extract_extension_name(name: str) -> str:
    """Derive an extension name from a migration class name.

    Update ``__extension__`` in the generated stub if necessary.
    """
    snake = Str.snake(name).removesuffix("_extension")
    for prefix in _EXTENSION_PREFIXES:
        if snake.startswith(prefix):
            snake = snake[len(prefix) :]
            break
    return snake


# Operations whose presence in ``up()`` forces a non-trivial ``down()``.
DESTRUCTIVE_OPS: frozenset[str] = frozenset(
    {
        "drop",
        "drop_column",
        "drop_index",
        "drop_if_exists",
        "drop_table",
    }
)


class Migration(ABC):
    """Base class for a migration file.

    Subclasses implement ``async def up(self) -> None`` and
    ``async def down(self) -> None``. ``__init_subclass__`` runs a static
    reversibility check: if ``up`` calls any destructive op, the
    ``down`` body must be non-empty.
    """

    def __init_subclass__(cls, **kw: object) -> None:
        super().__init_subclass__(**kw)
        # Skip the check for the abstract base or test stand-ins that don't
        # define their own up/down.
        if cls is Migration:
            return
        if "up" not in cls.__dict__ or "down" not in cls.__dict__:
            return
        try:
            up_src = inspect.getsource(cls.up)
            down_src = inspect.getsource(cls.down)
        except OSError, TypeError:  # pragma: no cover — defensive
            return
        destructive = _find_destructive_op(up_src)
        if destructive and _is_empty_function(down_src):
            raise MigrationNotReversibleError(cls.__name__, destructive)

    @abstractmethod
    async def up(self) -> None: ...

    @abstractmethod
    async def down(self) -> None: ...


def _find_destructive_op(source: str) -> str | None:
    """Return the first destructive op-name called in ``source``, or None."""
    try:
        tree = ast.parse(_dedent(source))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _attr_tail(node.func)
            if name in DESTRUCTIVE_OPS:
                return name
    return None


def _is_empty_function(source: str) -> bool:
    """Return True when the function body is empty / pass / docstring-only / not-implemented."""
    try:
        tree = ast.parse(_dedent(source))
    except SyntaxError:
        return True
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = list(node.body)
            # Strip leading docstring.
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            if not body:
                return True
            # All bodies of `pass`?
            if all(isinstance(stmt, ast.Pass) for stmt in body):
                return True
            # Single `raise NotImplementedError(...)`?
            if (
                len(body) == 1
                and isinstance(body[0], ast.Raise)
                and isinstance(body[0].exc, (ast.Call, ast.Name))
                and "NotImplementedError" in ast.dump(body[0].exc)
            ):
                return True
            return False
    return True


def _attr_tail(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _dedent(source: str) -> str:
    """Remove the common leading whitespace so ast.parse succeeds inside class bodies."""
    import textwrap

    return textwrap.dedent(source)


def discover_migrations(path: Path) -> Iterator[Path]:
    """Yield migration files in ``path`` sorted by name (filename = timestamp prefix)."""
    if not path.exists():
        return
    yield from sorted(path.glob("*.py"))


__all__ = [
    "DESTRUCTIVE_OPS",
    "Migration",
    "MigrationNotReversibleError",
    "discover_migrations",
    "extract_extension_name",
    "extract_table_name",
    "extract_view_name",
]

"""Typed bridge for typer.Argument and typer.Option.

click.ParamType is Generic[T] without a TypeVar default; pyright fills Unknown in the
overload that takes click_type, making Argument/Option "partially unknown" on the typer
module. Routing access through an Any-typed alias confines that at this single boundary.
"""

from collections.abc import Callable
from typing import Any

import typer as _typer

# typer.Argument/Option are factory callables returning sentinel default values
# used as `name: str = Argument(...)`. The return is genuinely any-typed (it
# stands in for whatever param it defaults), so the Any is confined to the
# return; the symbols themselves are typed as callables, not bare Any.
_mod: Any = _typer
Argument: Callable[..., Any] = _mod.Argument
Option: Callable[..., Any] = _mod.Option

__all__ = ["Argument", "Option"]

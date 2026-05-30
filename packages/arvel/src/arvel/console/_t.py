"""Typed bridge for typer.Argument and typer.Option.

click.ParamType is Generic[T] without a TypeVar default; pyright fills Unknown in the
overload that takes click_type, making Argument/Option "partially unknown" on the typer
module. Routing access through an Any-typed alias confines that at this single boundary.
"""

from typing import Any

import typer as _typer

_mod: Any = _typer
Argument: Any = _mod.Argument
Option: Any = _mod.Option

__all__ = ["Argument", "Option"]

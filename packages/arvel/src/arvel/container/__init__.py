"""Service container — auto-wiring DI with scopes, contextual bindings, tagging."""

from arvel.container.container import Container, ContextualBuilder
from arvel.container.errors import (
    AsyncBindingError,
    BindingResolutionError,
    CircularDependencyError,
)
from arvel.container.scopes import Scope

__all__ = [
    "AsyncBindingError",
    "BindingResolutionError",
    "CircularDependencyError",
    "Container",
    "ContextualBuilder",
    "Scope",
]

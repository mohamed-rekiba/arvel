"""Route model binding — auto-resolve path parameters to model instances.

Provides a dependency that inspects route path params and resolves them
to ORM model instances via the repository layer.
"""

from __future__ import annotations

from fastapi import Depends, Request  # noqa: TC002

from arvel.http.exceptions import ModelNotFoundError
from arvel.logging import Log

logger = Log.named("arvel.http.model_binding")

_bindings: dict[str, tuple[type, type]] = {}


def bind_model(
    param_name: str,
    model_cls: type,
    repository_cls: type,
) -> None:
    """Register an explicit model binding.

    Maps a route parameter name to a model class and its repository.
    """
    _bindings[param_name] = (model_cls, repository_cls)


def clear_bindings() -> None:
    """Remove all registered model bindings. Primarily for testing."""
    _bindings.clear()


def resolve_model[T](
    model_cls: type[T],
    *,
    param: str = "id",
    repository_cls: type | None = None,
) -> T:
    """Return a FastAPI Depends that resolves a path param to a model instance.

    Fetches the model from the request-scoped container's repository.
    Returns 404 if the model doesn't exist.
    """

    async def _resolver(request: Request) -> T:
        identifier = request.path_params.get(param)
        if identifier is None:
            raise ModelNotFoundError(model_cls.__name__, "")

        container = getattr(request.state, "container", None)
        if container is None:
            raise RuntimeError(
                "No request-scoped container found. Is RequestContainerMiddleware installed?"
            )

        repo_cls = repository_cls
        if repo_cls is None:
            binding = _bindings.get(param)
            if binding is not None:
                _, repo_cls = binding

        if repo_cls is None:
            raise RuntimeError(
                f"No repository registered for model binding param '{param}'. "
                "Use bind_model() or pass repository_cls explicitly."
            )

        repo = await container.resolve(repo_cls)
        instance = await repo.find(int(identifier))
        if instance is None:
            raise ModelNotFoundError(model_cls.__name__, str(identifier))

        return instance  # type: ignore[return-value]

    from typing import cast

    return cast("T", Depends(_resolver))

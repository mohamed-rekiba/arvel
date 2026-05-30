"""CanMiddleware — enforce a Gate ability on every request."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from arvel.auth.exceptions import AuthorizationException, UnauthenticatedException
from arvel.auth.gate import Gate
from arvel.container.container import Container


class CanMiddleware:
    def __init__(
        self,
        ability: str,
        *,
        gate: Gate | None = None,
        model_param: str | None = None,
    ) -> None:
        self._gate = gate
        self._ability = ability
        self._model_param = model_param

    async def handle(self, request: Any, call_next: Any) -> Any:
        user = getattr(getattr(request, "state", None), "user", None)
        if user is None:
            raise UnauthenticatedException("Authentication required.")
        gate = self._gate or self._resolve_gate(request)
        args = self._ability_args(request)
        if not await gate.allows(self._ability, user, *args):
            raise AuthorizationException(f"Not authorized to '{self._ability}'.")
        return await call_next(request)

    def _resolve_gate(self, request: Any) -> Gate:
        container_obj = getattr(
            getattr(getattr(request, "app", None), "state", None),
            "arvel_container",
            None,
        )
        if not isinstance(container_obj, Container):
            raise AuthorizationException("Authorization unavailable.")
        return container_obj.make(Gate)

    def _ability_args(self, request: Any) -> tuple[Any, ...]:
        if self._model_param is None:
            return ()
        path_params_obj: object = getattr(request, "path_params", {})
        if not isinstance(path_params_obj, Mapping):
            return ()
        path_params = cast("Mapping[str, object]", path_params_obj)
        return (path_params.get(self._model_param),)


Can = CanMiddleware


__all__ = ["Can", "CanMiddleware"]

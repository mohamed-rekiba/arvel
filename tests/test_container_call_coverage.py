"""arvel.kernel.container.Container.call — dependency-injecting invocation: skips ``self`` and
var-args, falls back to defaults, and injects container-resolvable annotations."""

from __future__ import annotations

from typing import Any

from arvel.kernel.container import Container


class _Service:
    def run(self, x: int = 5, *args: Any, **kwargs: Any) -> int:
        # self skipped, *args/**kwargs skipped, x served from its default
        return x


def test_call_bound_method_skips_self_and_varargs_uses_default() -> None:
    c = Container()
    assert c.call((_Service(), "run")) == 5


def test_call_plain_function_with_only_varargs() -> None:
    c = Container()

    def handler(*args: Any, **kwargs: Any) -> str:
        return "ok"

    assert c.call(handler) == "ok"


def test_call_injects_explicit_params_over_defaults() -> None:
    c = Container()

    def handler(a: int = 1, b: int = 2) -> int:
        return a + b

    assert c.call(handler, a=10) == 12  # a from params, b from default

"""Gate.after() — a hook that runs after the ability/policy check and can override the result
(Laravel Gate::after). Runs even when a before() hook short-circuited."""

from __future__ import annotations

from typing import Any

from arvel.auth.gate import Gate


async def test_after_overrides_allow_to_deny() -> None:
    gate = Gate()
    gate.define("edit", lambda u, *a: True)
    gate.after(lambda u, ability, result, args: False if ability == "edit" else None)
    assert await gate.allows("edit", user="alice") is False


async def test_after_grants_when_ability_undefined() -> None:
    gate = Gate()  # no ability defined → check denies; after flips it
    gate.after(lambda u, ability, result, args: True)
    assert await gate.allows("anything", user="bob") is True


async def test_after_runs_even_after_before_shortcircuit() -> None:
    gate = Gate()
    gate.before(lambda u, ability: True)  # super-admin allow
    gate.after(lambda u, ability, result, args: False)  # but read-only mode denies
    assert await gate.allows("edit", user="root") is False


async def test_after_returning_none_keeps_result() -> None:
    gate = Gate()
    gate.define("view", lambda u, *a: True)
    gate.after(lambda u, ability, result, args: None)
    assert await gate.allows("view", user="x") is True


async def test_after_receives_result_and_args() -> None:
    seen: dict[str, Any] = {}

    def record(user: Any, ability: str, result: Any, args: tuple[Any, ...]) -> None:
        seen.update(user=user, ability=ability, result=result, args=args)

    gate = Gate()
    gate.define("update", lambda u, post: True)
    gate.after(record)
    await gate.allows("update", "the-post", user="ada")
    assert seen == {"user": "ada", "ability": "update", "result": True, "args": ("the-post",)}

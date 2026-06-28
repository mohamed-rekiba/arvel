"""Views (doc 09/15) — the `can`/`cannot` template helpers delegate to the Gate."""

from __future__ import annotations

from typing import Any

from arvel.kernel import Application, set_application
from arvel.views import ViewFactory


class FakeGate:
    def __init__(self, allow: bool) -> None:
        self._allow = allow

    async def allows(self, ability: str, *args: Any, user: Any = None) -> bool:
        return self._allow


async def _render(src: str) -> str:
    out: str = await ViewFactory().env.from_string(src).render_async()
    return out


async def test_can_true_when_gate_allows() -> None:
    app = Application()
    app.instance("gate", FakeGate(allow=True))
    set_application(app)
    try:
        assert await _render("{{ 'Y' if can('update', 1) else 'N' }}") == "Y"
        assert await _render("{{ 'Y' if cannot('update', 1) else 'N' }}") == "N"
    finally:
        set_application(None)


async def test_can_false_when_gate_denies() -> None:
    app = Application()
    app.instance("gate", FakeGate(allow=False))
    set_application(app)
    try:
        assert await _render("{{ 'Y' if can('update') else 'N' }}") == "N"
        assert await _render("{{ 'Y' if cannot('update') else 'N' }}") == "Y"
    finally:
        set_application(None)


async def test_can_safe_without_gate() -> None:
    set_application(None)
    assert await _render("{{ 'Y' if can('update') else 'N' }}") == "N"  # degrades to denied

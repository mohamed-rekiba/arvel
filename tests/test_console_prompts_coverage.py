"""arvel.console.prompts.Prompter — the production (unseeded) branch of each prompt verb, which
falls through to ``click``. Driven with ``click.prompt``/``click.confirm`` monkeypatched."""

from __future__ import annotations

from typing import Any

import click
import pytest

from arvel.console.prompts import Prompter


@pytest.fixture
def click_stub(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {}

    def fake_prompt(label: str, **kwargs: Any) -> str:
        calls["prompt"] = (label, kwargs)
        return "typed"

    def fake_confirm(label: str, **kwargs: Any) -> bool:
        calls["confirm"] = (label, kwargs)
        return True

    monkeypatch.setattr(click, "prompt", fake_prompt)
    monkeypatch.setattr(click, "confirm", fake_confirm)
    return calls


def test_unseeded_prompter_falls_through_to_click(click_stub: dict[str, Any]) -> None:
    p = Prompter()  # unseeded -> production path
    assert p.ask("Name?", default="d") == "typed"
    assert p.secret("Password?") == "typed"
    assert p.confirm("Sure?", default=True) is True
    assert p.choice("Pick", ["a", "b"], default="a") == "typed"
    assert p.anticipate("City", ["NYC", "LA"]) == "typed"
    # anticipate builds a "label (suggestions)" hint
    assert "NYC" in click_stub["prompt"][0]


def test_anticipate_without_suggestions_uses_bare_label(click_stub: dict[str, Any]) -> None:
    assert Prompter().anticipate("City", []) == "typed"
    assert click_stub["prompt"][0] == "City"

"""Prompts (CLI-3, Laravel Prompts parity): ask/secret/confirm/choice/anticipate — driven by an
injectable `Prompter` so tests seed answers without touching real stdin."""

from __future__ import annotations

import pytest

from arvel.console import Command
from arvel.console.prompts import Prompter, anticipate, ask, choice, confirm, secret


def test_ask_returns_the_seeded_answer() -> None:
    assert ask("Name?", prompter=Prompter(["Ada"])) == "Ada"


def test_ask_falls_back_to_default_on_a_blank_seeded_answer() -> None:
    assert ask("Name?", default="world", prompter=Prompter([""])) == "world"


def test_secret_returns_the_seeded_answer_without_echoing() -> None:
    assert secret("Password?", prompter=Prompter(["hunter2"])) == "hunter2"


def test_confirm_parses_seeded_yes_no() -> None:
    assert confirm("Proceed?", prompter=Prompter(["y"])) is True
    assert confirm("Proceed?", prompter=Prompter(["n"])) is False
    assert confirm("Proceed?", default=True, prompter=Prompter([""])) is True


def test_choice_restricts_to_the_option_set() -> None:
    assert choice("Pick", ["red", "green", "blue"], prompter=Prompter(["green"])) == "green"


def test_choice_reprompts_on_invalid_input() -> None:
    # "purple" isn't an option — re-prompts through the seeded list until "blue" lands
    picked = choice("Pick", ["red", "green", "blue"], prompter=Prompter(["purple", "blue"]))
    assert picked == "blue"


def test_choice_raises_when_seeded_answers_are_exhausted_without_a_valid_pick() -> None:
    with pytest.raises(ValueError, match="exhausted"):
        choice("Pick", ["red", "green"], prompter=Prompter(["nope", "still-nope"]))


def test_anticipate_accepts_any_free_text_not_just_suggestions() -> None:
    assert anticipate("City?", ["Cairo", "Paris"], prompter=Prompter(["Nowhere"])) == "Nowhere"


def test_command_prompt_methods_use_its_injected_prompter() -> None:
    class Setup(Command):
        async def handle(self) -> str:
            name = self.ask("Name?")
            proceed = self.confirm("Go?")
            return f"{name}:{proceed}"

    cmd = Setup(prompter=Prompter(["Ada", "y"]))
    import asyncio

    assert asyncio.run(cmd.handle()) == "Ada:True"

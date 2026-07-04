"""arvel.console.prompts — Laravel Prompts parity: ask/secret/confirm/choice/anticipate.

Built on click's prompt primitives (already vendored via typer — no new dependency), imported
lazily so this stays cheap to import. Each function takes an optional injectable ``prompter``
(:class:`Prompter`) so tests pre-seed answers without touching real stdin; production code omits
it and gets the real terminal. Blocking — a human is waiting either way, so there's no benefit to
threading these off the event loop; safe to call from an async ``Command.handle``.
"""

from __future__ import annotations

from collections.abc import Sequence


class Prompter:
    """The prompt driver. ``Prompter()`` (no ``answers``) reads the real terminal via click;
    ``Prompter(["a", "b", ...])`` (tests) answers each successive prompt call from the list in
    order — an empty seeded answer means "accept the default"."""

    def __init__(self, answers: Sequence[str] | None = None) -> None:
        self._answers = list(answers) if answers is not None else None
        self._i = 0

    def _next(self) -> str | None:
        """The next seeded answer, or ``None`` when unseeded (production mode — fall through to
        the real terminal). A seeded-but-exhausted list answers with ``""`` (→ the default)."""
        if self._answers is None:
            return None
        value = self._answers[self._i] if self._i < len(self._answers) else ""
        self._i += 1
        return value

    def ask(self, label: str, default: str | None = None) -> str:
        seeded = self._next()
        if seeded is not None:
            return seeded or (default or "")
        import click

        return str(click.prompt(label, default=default or "", show_default=bool(default)))

    def secret(self, label: str) -> str:
        seeded = self._next()
        if seeded is not None:
            return seeded
        import click

        return str(click.prompt(label, hide_input=True))

    def confirm(self, label: str, default: bool = False) -> bool:
        seeded = self._next()
        if seeded is not None:
            return seeded.strip().lower() in ("y", "yes", "true", "1") if seeded else default
        import click

        return click.confirm(label, default=default)

    def choice(self, label: str, options: Sequence[str], default: str | None = None) -> str:
        if (
            self._answers is not None
        ):  # seeded (tests) — re-prompt through the list until a valid pick
            while True:
                seeded = self._next()
                if seeded is not None and seeded in options:
                    return seeded
                if self._i >= len(self._answers):
                    message = (
                        f"choice {label!r}: seeded answers exhausted without a valid pick "
                        f"from {list(options)!r}"
                    )
                    raise ValueError(message)
        import click

        return str(
            click.prompt(
                label, type=click.Choice(list(options)), default=default, show_choices=True
            )
        )

    def anticipate(self, label: str, suggestions: Sequence[str], default: str | None = None) -> str:
        """Free-text with suggestions shown as a hint (Laravel ``suggest``/``anticipate``) — unlike
        :meth:`choice`, any answer is accepted."""
        seeded = self._next()
        if seeded is not None:
            return seeded or (default or "")
        import click

        hint = f"{label} ({', '.join(suggestions)})" if suggestions else label
        return str(click.prompt(hint, default=default or "", show_default=bool(default)))


def ask(label: str, default: str | None = None, *, prompter: Prompter | None = None) -> str:
    return (prompter or Prompter()).ask(label, default)


def secret(label: str, *, prompter: Prompter | None = None) -> str:
    return (prompter or Prompter()).secret(label)


def confirm(label: str, default: bool = False, *, prompter: Prompter | None = None) -> bool:
    return (prompter or Prompter()).confirm(label, default)


def choice(
    label: str,
    options: Sequence[str],
    default: str | None = None,
    *,
    prompter: Prompter | None = None,
) -> str:
    return (prompter or Prompter()).choice(label, options, default)


def anticipate(
    label: str,
    suggestions: Sequence[str],
    default: str | None = None,
    *,
    prompter: Prompter | None = None,
) -> str:
    return (prompter or Prompter()).anticipate(label, suggestions, default)

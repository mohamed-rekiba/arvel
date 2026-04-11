"""Interactive prompts for the `arvel new` command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config import _SERVICE_LABELS, _VALID_CHOICES, PRESETS

if TYPE_CHECKING:
    from rich.console import Console

    from arvel.cli.ui import InquirerPreloader


def _prompt_select(message: str, choices: list[dict[str, str]], default: str | None = None) -> str:
    """Arrow-key select prompt via InquirerPy."""
    from InquirerPy import inquirer

    return inquirer.select(  # type: ignore[no-any-return]
        message=message,
        choices=choices,
        default=default,
        pointer="❯",  # noqa: RUF001
        show_cursor=False,
    ).execute()


def _preset_summary(preset_name: str) -> str:
    """One-line summary of a preset's driver choices."""
    p = PRESETS[preset_name]
    return ", ".join(f"{p[k]}" for k in _SERVICE_LABELS)


def _run_interactive_prompts(
    *,
    cli_database: str,
    cli_cache: str,
    cli_queue: str,
    cli_mail: str,
    cli_storage: str,
    cli_search: str,
    cli_broadcast: str,
    cli_preset: str | None,
    console: Console,
    preloader: InquirerPreloader,
) -> dict[str, str]:
    """Interactive stack selection. CLI-supplied values aren't re-prompted."""
    cli_overrides: dict[str, str] = {}
    defaults = PRESETS["minimal"]
    service_to_cli = {
        "database": cli_database,
        "cache": cli_cache,
        "queue": cli_queue,
        "mail": cli_mail,
        "storage": cli_storage,
        "search": cli_search,
        "broadcast": cli_broadcast,
    }

    for svc, cli_val in service_to_cli.items():
        if cli_val != defaults[svc]:
            cli_overrides[svc] = cli_val

    if cli_preset and cli_preset in PRESETS:
        choices = {**PRESETS[cli_preset], **cli_overrides}
    elif cli_overrides:
        choices = {**defaults, **cli_overrides}
        return choices
    else:
        preset_choices = [
            {"name": f"Minimal    — {_preset_summary('minimal')}", "value": "minimal"},
            {"name": f"Standard   — {_preset_summary('standard')}", "value": "standard"},
            {"name": f"Full       — {_preset_summary('full')}", "value": "full"},
            {"name": "Custom     — choose each service individually", "value": "custom"},
        ]

        inquirer = preloader.get()
        selected: str = inquirer.select(
            message="Choose your stack:",
            choices=preset_choices,
            default="minimal",
            pointer="❯",  # noqa: RUF001
            show_cursor=False,
        ).execute()

        if selected == "custom":
            choices = _run_custom_prompts(cli_overrides)
        else:
            choices = {**PRESETS[selected], **cli_overrides}

    _print_summary(choices, console)
    return choices


def _run_custom_prompts(cli_overrides: dict[str, str]) -> dict[str, str]:
    """Prompt each service one-by-one, skipping CLI overrides."""
    choices: dict[str, str] = {}
    defaults = PRESETS["minimal"]

    for svc, label in _SERVICE_LABELS.items():
        if svc in cli_overrides:
            choices[svc] = cli_overrides[svc]
            continue
        configs = _VALID_CHOICES[svc]
        option_list = [{"name": k, "value": k} for k in configs]
        choices[svc] = _prompt_select(f"{label}:", option_list, default=defaults[svc])

    return choices


def _print_summary(choices: dict[str, str], console: Console) -> None:
    """Print the selected stack as a one-liner."""
    parts = [f"[green]{choices[svc]}[/green]" for svc in _SERVICE_LABELS]
    summary = " · ".join(parts)
    console.print()
    console.print(f"  [bold]Stack:[/bold] {summary}")
    console.print()

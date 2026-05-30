# CLI Prompts

Arvel's console layer is built on **Typer**, which ships prompting out of the box:

```python
import typer

from arvel.console import Command


class InstallCommand(Command):
    name = "app:install"

    def handle(self) -> None:
        db_url = typer.prompt("Database URL", default="postgresql://localhost/myapp")
        if typer.confirm("Run migrations now?"):
            # ...
```

For richer interactions (select menus, checkboxes, autocomplete), **questionary** integrates cleanly:

```bash
uv add questionary
```

```python
import questionary

choice = questionary.select("Which driver?", choices=["redis", "database", "sync"]).ask()
```

## See also

- [Console](console.md) — command authoring reference.

# Console Tests

Console commands are subclasses of `arvel.console.Command` registered with a Typer app. Test them with the standard `typer.testing.CliRunner`, driving the same `build_app()` factory the production CLI uses.

## Building the CLI under test

`arvel.console.entrypoint.build_app()` discovers every command from the `arvel.commands` entry-point group and returns the Typer app. That's the same factory `arvel` uses, so what your tests exercise is what users invoke:

```python
from typer.testing import CliRunner

from arvel.console.entrypoint import build_app


runner = CliRunner()
cli = build_app()


def test_about_command_prints_version() -> None:
    result = runner.invoke(cli, ["about"])
    assert result.exit_code == 0
    assert "arvel" in result.stdout
```

For provider-attached commands (anything in `ServiceProvider.commands()`), the framework Application has to be booted before they're visible — boot the app yourself and feed its commands into a fresh `Application`:

```python
from arvel.console import Application as ConsoleApplication

from app.bootstrap import create_application


async def test_invoices_send_dispatches_jobs() -> None:
    app = await create_application()
    cli = app.container.make(ConsoleApplication).typer_app

    result = runner.invoke(cli, ["invoices:send", "--month", "2026-05"])
    assert result.exit_code == 0
```

## Asserting on side effects

Combine the CLI runner with [Bus.fake()](mocking.md):

```python
async def test_invoices_send_dispatches_jobs() -> None:
    Bus.fake()
    await InvoiceFactory().count(3).create(month="2026-05")

    result = runner.invoke(cli, ["invoices:send", "--month", "2026-05"])
    assert result.exit_code == 0

    Bus.assert_dispatched_count(SendInvoice, 3)
```

## Testing interactive prompts

`CliRunner.invoke` accepts an `input` string to simulate stdin:

```python
def test_confirms_destructive_action() -> None:
    result = runner.invoke(cli, ["cache:clear"], input="yes\n")
    assert result.exit_code == 0
```

## Testing with environment variables

```python
def test_key_generate_show_prints_a_key() -> None:
    result = runner.invoke(cli, ["key:generate", "--show"])
    assert result.exit_code == 0
    assert result.stdout.startswith("base64:")
```

## Asserting exit codes

The built-in commands follow the same exit-code contract:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | The command body raised |
| `2` | Bootstrap / input failure |

```python
def test_db_seed_invalid_name_exits_2() -> None:
    result = runner.invoke(cli, ["db:seed", "--seeder", "../etc/passwd"])
    assert result.exit_code == 2
    assert "invalid --seeder" in result.stderr
```

## See also

- [Console](console.md) — building console commands.
- [Testing → HTTP Tests](http-tests.md) — testing HTTP endpoints.
- [Testing → Mocking](mocking.md) — faking facades.

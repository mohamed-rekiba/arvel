"""key:rotate command — honest deferral until FB-022-002 lands.

The real implementation needs to walk every ``EncryptedType`` column across
the user's mapped tables, re-encrypt each row's payload with the new key, and
update the row in a transactional batch. That work — including the schema
discovery, batching strategy, and production guard semantics — is scheduled
for FB-022-002 and intentionally NOT shipped in WI-021.

This command exists at the entry-point so users discover it via
``arvel --help`` and get an actionable pointer rather than a missing-command
error. Invoking it exits 2 with a clear NotImplementedError-style message.
"""

from __future__ import annotations

from typing import Annotated

import typer

from arvel.console import Command, Context
from arvel.console._t import Option as _Option


class KeyRotateCommand(Command):
    name = "key:rotate"
    help = "Re-encrypt all encrypted columns with a new key (not yet implemented)"

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            old_key: Annotated[str, _Option("--old-key", help="Current encryption key")] = "",
            new_key: Annotated[str, _Option("--new-key", help="Replacement encryption key")] = "",
            *,
            force: Annotated[bool, _Option("--force", help="Bypass production guard")] = False,
        ) -> None:
            _ = old_key, new_key  # accepted for forward compatibility
            from arvel.config import config  # noqa: PLC0415

            if config("app.is_production", default=False) and not force:
                typer.echo(
                    "ERROR: key:rotate is blocked in production. Pass --force to override.",
                    err=True,
                )
                raise typer.Exit(2)
            code = cmd_self.handle(Context())
            raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        ctx.error(
            "key:rotate is not yet implemented.\n"
            "\n"
            "Re-encrypting EncryptedType columns with a new key needs schema "
            "discovery, transactional batching, and a verified production guard. "
            "Tracked in FB-022-002.\n"
            "\n"
            "Workaround: rotate APP_KEY by re-encrypting affected columns "
            "manually in a one-off migration."
        )
        return 2

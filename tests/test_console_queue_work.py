"""Console (doc 13) — queue:work resolves + runs the bound queue manager's worker."""

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


def test_queue_work_invokes_manager_work() -> None:
    from arvel.kernel import Application, set_application

    class FakeManager:
        def __init__(self) -> None:
            self.queues: Any = None

        async def work(self, queues: Any = None) -> None:
            self.queues = queues

    fake = FakeManager()
    app = Application()
    app.instance("queue", fake)
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["queue:work", "--queue", "default,mail"])
        assert result.exit_code == 0, result.output
        assert fake.queues == ["default", "mail"]
    finally:
        set_application(None)


def test_queue_work_without_queue_errors() -> None:
    from arvel.kernel import Application, set_application

    set_application(Application())  # active app, but no 'queue' bound → binding-missing branch
    try:
        result = runner.invoke(build_cli(), ["queue:work"])
        assert result.exit_code == 1
        assert "no queue bound" in result.output
    finally:
        set_application(None)

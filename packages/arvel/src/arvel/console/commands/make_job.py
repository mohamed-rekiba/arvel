"""``make:job`` — generate a Pydantic queued job.

Arvel jobs are Pydantic models that auto-register in ``JobRegistry``.
Payload fields are declared on the subclass; queue metadata
(``queue``, ``tries``, ``timeout``, ``delay``, ``priority``) is
inherited from :class:`arvel.queue.Job` and can be overridden as
class-level defaults.

Dispatch with ``await Bus.dispatch(MyJob(...))``.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — queued job."""

from __future__ import annotations

from arvel.queue import Job


class {title}(Job):
    """Background work executed by an arvel queue worker."""

    queue: str = "default"
    tries: int = 3
    timeout: int = 60

    # Declare payload fields here, e.g.:
    # user_id: int
    # template: str

    async def handle(self) -> None:
        """Run the job. Raise to fail; ``tries`` controls retries."""
'''


class MakeJobCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:job"
    help: ClassVar[str] = "Generate a queued Job (Pydantic + handle())"
    _target_subdir: ClassVar[str] = "app/jobs"

    def _render(self, name: str) -> str:
        title = Str.pascal(name)
        return _TEMPLATE.format(title=title)

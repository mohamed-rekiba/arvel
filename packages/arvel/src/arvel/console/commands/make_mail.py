"""``make:mail`` — generate a Mailable class.

Mailables describe an email in two parts:

- :meth:`envelope` returns an :class:`arvel.mail.Envelope` with addressing
  (``from_address``, ``to``, ``subject``, optional ``cc``/``bcc``/``reply_to``/``tags``).
- :meth:`content` returns an :class:`arvel.mail.Content`. Supply an inline
  string or a Jinja2 template name for either or both of HTML and plain
  text — at least one body source must be set.

File attachments come from the optional :meth:`attachments` override.

Send with ``await Mail.send(MyMail(...))``.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — mailable email message."""

from __future__ import annotations

from arvel.mail import Content, Envelope, Mailable


class {title}(Mailable):
    """Outbound email message."""

    def envelope(self) -> Envelope:
        return Envelope(
            from_address="hello@example.com",
            to=["recipient@example.com"],
            subject="{name}",
        )

    def content(self) -> Content:
        return Content(
            html_view="mail/{name}.html.j2",
            text_view="mail/{name}.txt.j2",
            data={{}},
        )
'''


class MakeMailCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:mail"
    help: ClassVar[str] = "Generate a Mailable (envelope() + content())"
    _target_subdir: ClassVar[str] = "app/mail"

    def _render(self, name: str) -> str:
        title = Str.pascal(name)
        return _TEMPLATE.format(title=title, name=name)

"""Content dataclass — email body definition.

A ``Content`` describes what goes inside the email envelope. Bodies come
in two flavours and two delivery modes:

- **Inline**: ``text=`` and ``html=`` carry the body as a literal string.
 No template rendering is performed; the string is used verbatim.
- **Template**: ``text_view=`` and ``html_view=`` are Jinja2 template
 names resolved via :mod:`arvel.support.view`. ``data=`` carries the
 template context shared between both views.

Validation:

- ``text`` and ``text_view`` are mutually exclusive.
- ``html`` and ``html_view`` are mutually exclusive.
- At least one of the four body sources must be set.

Typical shapes::

 Content(text="Hi! Thanks for signing up.") # text only
 Content(html="<p>Hi! Thanks.</p>") # html only — text auto-derived
 Content(html_view="welcome.html.j2", text_view="welcome.txt.j2", # both via templates
 data={"name": user.name})

When only an HTML body is supplied, the mailer auto-derives a plain-text
alternative (see :mod:`arvel.support.html_to_text`). For accessibility
and spam-scoring reasons, providing both formats explicitly is
recommended for any mailable used outside ad-hoc scripts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _empty_data() -> dict[str, Any]:
    return {}


@dataclass
class Content:
    """Email body. See module docstring for the validation contract."""

    text: str | None = None
    text_view: str | None = None
    html: str | None = None
    html_view: str | None = None
    data: dict[str, Any] = field(default_factory=_empty_data)

    def __post_init__(self) -> None:
        if self.text is not None and self.text_view is not None:
            raise ValueError(
                "Content: 'text' and 'text_view' are mutually exclusive — "
                "supply an inline string or a template name, not both.",
            )
        if self.html is not None and self.html_view is not None:
            raise ValueError(
                "Content: 'html' and 'html_view' are mutually exclusive — "
                "supply an inline string or a template name, not both.",
            )
        if (
            self.text is None
            and self.text_view is None
            and self.html is None
            and self.html_view is None
        ):
            raise ValueError(
                "Content: at least one of 'text', 'text_view', 'html', or 'html_view' must be set.",
            )


__all__ = ["Content"]

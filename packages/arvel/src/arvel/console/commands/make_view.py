"""``make:view`` — generate a Jinja view template.

Arvel doesn't bundle a templating engine; the convention is **Jinja2**
through FastAPI's ``Jinja2Templates`` integration. The default stub
extends ``layouts/base.html`` so views slot into a shared layout — add
the layout file at ``resources/views/layouts/base.html`` if your app
doesn't have one yet.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = """{{% extends "layouts/base.html" %}}

{{% block title %}}{title}{{% endblock %}}

{{% block content %}}
  <h1>{title}</h1>
  <p>Replace this content with your own markup.</p>
{{% endblock %}}
"""


class MakeViewCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:view"
    help: ClassVar[str] = "Generate a Jinja view template (extends layouts/base.html)"
    _target_subdir: ClassVar[str] = "resources/views"
    _extension: ClassVar[str] = ".html.jinja"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))

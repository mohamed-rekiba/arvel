"""View / template rendering configuration.

``paths`` lists the directories Jinja2 searches when ``render_template``
is called (mailables, ``View::make`` helpers, etc.). Paths may be
absolute or relative; relative paths resolve against the project root.

The default ``resources/views`` directory matches the convention used by
``make:view`` so generated templates are picked up automatically. Add
more directories (e.g. ``app/templates``) if you keep templates near
their owning module.
"""

from __future__ import annotations

paths: list[str] = ["resources/views"]

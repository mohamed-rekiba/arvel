"""ASGI entrypoint — expose the application to the server.

Run with::

    uv run uvicorn public.asgi:asgi --reload

``Application.into_asgi()`` owns the lifespan: it boots providers on
startup and runs shutdown when the server stops.
"""

from __future__ import annotations

from bootstrap.app import create_application

asgi = create_application().into_asgi()

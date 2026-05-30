"""ASGI entrypoint for the e-commerce demo."""

from __future__ import annotations

from bootstrap.app import create_application, create_asgi

asgi = create_asgi(create_application())

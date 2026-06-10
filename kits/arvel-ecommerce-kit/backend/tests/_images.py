"""Single source of truth for the e-commerce kit's container image pins.

Pins match the framework's emulator images (see
``packages/arvel/tests/integration/emulators/_images.py``) so the kit is
tested against the same versions the framework validates.

Both the testcontainers harness (``conftest.py`` imports the constants) and
the GitHub Actions ``ecommerce-kit`` job (via the ``__main__`` block below)
read their image references from here. Running the module as a script prints
one image per line — designed for parallel ``docker pull`` / ``docker save``.

* ``IMAGE_MOTO`` runs ``motoserver/moto`` speaking the S3 wire protocol —
  the same S3 emulator the framework's storage drivers test against.
* ``IMAGE_REDIS`` runs the ``valkey/valkey`` OSS Redis fork — wire
  compatible with the ``redis`` client and every Arvel Redis driver.

To bump a version: web-search the current stable tag per
``105-engineering-preferences.mdc``, update the relevant ``Final`` below, and
re-run the suite. Nothing else needs editing — the fixtures and CI workflow
dereference these constants automatically.
"""

from __future__ import annotations

from typing import Final

IMAGE_MOTO: Final[str] = "motoserver/moto:5.2.2"
IMAGE_REDIS: Final[str] = "valkey/valkey:9.1-alpine"
IMAGE_RABBITMQ: Final[str] = "rabbitmq:4.3-management-alpine"
IMAGE_MAILPIT: Final[str] = "axllent/mailpit:v1.30"
IMAGE_POSTGRES: Final[str] = "postgres:18.4-alpine"

ALL_IMAGES: Final[tuple[str, ...]] = (
    IMAGE_MOTO,
    IMAGE_REDIS,
    IMAGE_RABBITMQ,
    IMAGE_MAILPIT,
    IMAGE_POSTGRES,
)

__all__ = [
    "ALL_IMAGES",
    "IMAGE_MAILPIT",
    "IMAGE_MOTO",
    "IMAGE_POSTGRES",
    "IMAGE_RABBITMQ",
    "IMAGE_REDIS",
]


if __name__ == "__main__":
    for _img in ALL_IMAGES:
        print(_img)  # noqa: T201

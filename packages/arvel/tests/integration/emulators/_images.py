"""Single source of truth for emulator container image pins.

Both the pytest fixtures (via direct import) and the ``Makefile`` /
GitHub Actions ``integration`` job (via the ``__main__`` block at the
bottom of this file) read their image references from here. Running the
module as a script prints one image per line — designed for
``xargs -n1 -P`` style parallel ``docker pull`` invocations.

The constant names reflect the *protocol* the emulator speaks
(Redis-protocol, MySQL-protocol), not the specific implementation:

* ``IMAGE_REDIS`` runs the ``valkey/valkey`` OSS Redis fork — wire
  compatible with the ``redis`` Python client and every Arvel driver
  that talks Redis (cache, session, queue, broadcasting, reverb).
* ``IMAGE_MYSQL`` runs the ``mariadb`` OSS MySQL fork — wire compatible
  with ``aiomysql`` / ``pymysql`` and the ``mysql+<driver>://``
  SQLAlchemy URLs Arvel's SQL drivers emit.

To bump a version: web-search the current stable tag per
``105-engineering-preferences.mdc``, update the relevant ``Final``
below, and re-run ``make pull-emulators && make test-integration``.
Nothing else needs editing — the fixtures, Makefile, and CI workflow
all dereference these constants automatically.
"""

from __future__ import annotations

from typing import Final

IMAGE_MOTO: Final[str] = "motoserver/moto:5.2.1"
IMAGE_AZURITE: Final[str] = "mcr.microsoft.com/azure-storage/azurite:3.35.0"
IMAGE_FAKE_GCS: Final[str] = "fsouza/fake-gcs-server:1.54.0"
IMAGE_REDIS: Final[str] = "valkey/valkey:9.0.4-alpine3.23"
IMAGE_MAILPIT: Final[str] = "axllent/mailpit:v1.30.0"
IMAGE_POSTGRES: Final[str] = "postgres:18.3-alpine3.23"
IMAGE_MYSQL: Final[str] = "mariadb:11.8.6"
IMAGE_RABBITMQ: Final[str] = "rabbitmq:4.3.0-management-alpine"

ALL_IMAGES: Final[tuple[str, ...]] = (
    IMAGE_MOTO,
    IMAGE_AZURITE,
    IMAGE_FAKE_GCS,
    IMAGE_REDIS,
    IMAGE_MAILPIT,
    IMAGE_POSTGRES,
    IMAGE_MYSQL,
    IMAGE_RABBITMQ,
)

__all__ = [
    "ALL_IMAGES",
    "IMAGE_AZURITE",
    "IMAGE_FAKE_GCS",
    "IMAGE_MAILPIT",
    "IMAGE_MOTO",
    "IMAGE_MYSQL",
    "IMAGE_POSTGRES",
    "IMAGE_RABBITMQ",
    "IMAGE_REDIS",
]


if __name__ == "__main__":
    # One image per line — consumed by ``make pull-emulators`` and the
    # equivalent CI step via ``xargs``.
    for _img in ALL_IMAGES:
        print(_img)  # noqa: T201

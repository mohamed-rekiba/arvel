"""Migrations shipped with arvel-image.

Stub migrations for the polymorphic ``media`` table. Consumers copy them
into their app's ``database/migrations/`` directory via
``arvel vendor:publish --tag=arvel-image``; the migrator discovers them by
filesystem path, not by Python import.

Available migrations:

- ``create_media_table.py`` — the polymorphic ``media`` table that
  associates files (and their conversions) with any Arvel model.

The image-manipulation API (:class:`arvel_image.Image`) does not require
any database. Apps that only transform bytes can ignore this migration.
"""

"""Migrations shipped with arvel-permission.

Stub migrations for the Spatie-style authorization tables. Consumers copy
them into their app's ``database/migrations/`` directory; the migrator
discovers them by filesystem path, not by Python import.

Available migrations:

- ``create_permission_tables.py`` — roles, permissions, and the three
  pivot tables (``model_has_roles``, ``model_has_permissions``,
  ``role_has_permissions``).

The canonical ``users`` table itself ships with the framework as
``arvel.auth.migrations.create_users_table`` — authentication is the
framework's concern; authorization (this package) layers on top.
"""

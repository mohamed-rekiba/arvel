"""Framework migrations shipped with arvel.auth.

Stub migrations published into the consumer app via
``arvel vendor:publish --tag=arvel-auth``. They are discovered by the
migrator by filesystem path, not by Python import — this package is
intentionally import-free so adding a new file does not require updating
``__all__``.

Available migrations:

- ``create_users_table.py`` — canonical authenticatable model (Laravel parity).
- ``create_refresh_tokens_table.py`` — opaque refresh-token store (ADR-078).
- ``create_personal_access_tokens_table.py`` — token guard storage.
"""

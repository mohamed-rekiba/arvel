# WI-arvel-002 — no schema change

Stage 2c (DBA) is a no-op for this WI.

- Story 1 (Track E): test additions only, no schema impact.
- Story 2 (Track D): test additions only, no schema impact.
- Story 3 (Track F): integration test against existing schema (`media` table, `responsive_images` JSON column). Reads/writes only; no new columns, indexes, or constraints.
- Story 4 (CVE): `pyproject.toml` pin in a sibling package. No database touchpoint.

The existing `media` table schema (defined in `packages/arvel-image/src/arvel_image/migrations/create_media_table.py`) is unchanged.

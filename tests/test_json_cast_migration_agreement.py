"""DR-0062 fitness guard — model/migration column-type agreement: a ``TEXT_CASTS``-cast model
field (``json``/``array``/``collection``/``object``/``encrypted:*``) always binds as TEXT
(``_build_table``'s deliberate contract, so the cast's own (de)serialization never double-encodes
against a native column's processors). A shipped migration declaring that column native JSON
disagrees with the ORM's bind and 500s on Postgres — this is the check whose absence let that bug
ship. No DB needed: it inspects the Blueprint's compiled column types directly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sqlalchemy as sa

from arvel.database.migrations import Migration
from arvel.database.schema import Blueprint

_MIGRATIONS = Path("src/arvel/console/_skeleton/app/database/migrations")

# Every framework skeleton column whose owning model casts it through a TEXT_CASTS cast (so the ORM
# binds it TEXT). All must ship as t.text(), never t.json/jsonb. This list is maintained by hand today;
# the durable form derives it from the models (iterate the model registry, filter __casts__ through
# uses_text_column, map to the table's skeleton migration) so a NEW json-cast model can't slip a
# native-JSON migration past the check — the one gap that let DR-0062 ship. Tracked as a follow-up.
# (skeleton migration file, the TEXT_CASTS-cast column it declares)
_TEXT_CAST_COLUMNS = [
    ("0001_01_01_000008_create_features_table.py.tmpl", "value"),  # FeatureValue.value
    ("0001_01_01_000009_create_activity_log_table.py.tmpl", "properties"),  # Activity.properties
    ("0001_01_01_000007_create_job_batches_table.py.tmpl", "options"),  # JobBatch.options
    ("0001_01_01_000001_create_personal_access_tokens_table.py.tmpl", "abilities"),  # PAT.abilities
    ("0001_01_01_000004_create_notifications_table.py.tmpl", "data"),  # DatabaseNotification.data
]


def _load_migration(fname: str) -> Migration:
    ns: dict[str, Any] = {}
    path = _MIGRATIONS / fname
    exec(compile(path.read_text(), str(path), "exec"), ns)  # noqa: S102 - trusted skeleton template
    cls = next(
        v
        for v in ns.values()
        if isinstance(v, type) and issubclass(v, Migration) and v is not Migration
    )
    return cls()


class _CapturingSchema:
    """Stands in for ``Schema.create()`` minus the Alembic op — builds the same real
    ``sa.Column`` objects the migration would ship, with no DB connection at all."""

    def __init__(self) -> None:
        self.columns: dict[str, Any] = {}

    def create(self, name: str, define: Any) -> None:
        blueprint = Blueprint(name)
        define(blueprint)
        self.columns = {c.name: c.type for c in blueprint.core_columns()}


def test_text_cast_columns_are_declared_text_not_json_in_shipped_migrations() -> None:
    for fname, field in _TEXT_CAST_COLUMNS:
        schema = _CapturingSchema()
        _load_migration(fname).up(schema)
        col_type = schema.columns[field]
        assert isinstance(col_type, sa.Text), (
            f"{fname}::{field} compiles to {col_type!r}, not TEXT — a json-cast field's ORM bind "
            "is ALWAYS TEXT (_build_table's TEXT_CASTS contract, model.py:186); a JSON/JSONB "
            "column here 500s on Postgres (DR-0062)."
        )

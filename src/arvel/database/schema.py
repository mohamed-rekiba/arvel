"""arvel.database.schema — the Laravel-style ``Blueprint`` DSL over SQLAlchemy Core.

A ``Blueprint`` collects fluent column definitions (``t.id()``, ``t.string("title")``,
``t.foreign_id("user_id").constrained()``, ``t.timestamps()``, ``t.vector(...)``) and
compiles them to a real Core ``Table`` — so the same schema compiles to every dialect
and feeds Alembic. Raw-SQL DDL would be a spec violation (doc 08). SQLAlchemy is
lazy-imported. Grounded in knowledge/port/08-advanced-database.md.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

# A plain column name (vs an index expression like ``name->>'en'`` that must be wrapped as SQL text).
PLAIN_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def _big_integer_factory() -> Any:
    import sqlalchemy as sa

    return sa.BigInteger()


class ColumnDefinition:
    """A fluent column spec; ``to_core()`` materializes a SQLAlchemy ``Column``."""

    def __init__(self, name: str, type_factory: Any, *, primary_key: bool = False) -> None:
        self.name = name
        self._type_factory = type_factory
        self._primary_key = primary_key
        self._nullable = not primary_key
        self._unique = False
        self._index = False
        self._default: Any = None
        self._has_default = False
        self._foreign_key: str | None = None

    def nullable(self, *, flag: bool = True) -> ColumnDefinition:
        self._nullable = flag
        return self

    def not_null(self) -> ColumnDefinition:
        self._nullable = False
        return self

    def unique(self) -> ColumnDefinition:
        self._unique = True
        return self

    def index(self) -> ColumnDefinition:
        self._index = True
        return self

    def primary(self) -> ColumnDefinition:
        """Mark this column the primary key (Laravel ``->primary()``) — e.g. a non-integer
        ``t.uuid("id").primary()`` when the default auto-increment ``t.id()`` doesn't fit."""
        self._primary_key = True
        self._nullable = False
        return self

    def default(self, *, value: Any) -> ColumnDefinition:
        self._default = value
        self._has_default = True
        return self

    def constrained(self, table: str | None = None) -> ColumnDefinition:
        """Add a FK to ``{table}.id``; ``table`` defaults to the pluralized ``*_id`` name."""
        target = table or self._infer_table()
        self._foreign_key = f"{target}.id"
        return self

    def _infer_table(self) -> str:
        from arvel.support import Str

        base = self.name.removesuffix("_id")
        return Str.plural(base)

    def to_core(self) -> Any:
        import sqlalchemy as sa

        col_type = self._type_factory()
        args: list[Any] = [self.name, col_type]
        if self._foreign_key is not None:
            args.append(sa.ForeignKey(self._foreign_key))
        kwargs: dict[str, Any] = {
            "primary_key": self._primary_key,
            "nullable": self._nullable,
            "unique": self._unique or None,
            "index": self._index or None,
        }
        if self._primary_key:
            # a uuid/string PK must opt out of autoincrement, or SQLAlchemy rejects it (CHAR isn't autoincrementable)
            kwargs["autoincrement"] = isinstance(col_type, sa.Integer)
        if self._has_default:
            # a SERVER-side DDL default too, so raw inserts / ALTER TABLE ADD COLUMN honor it, not just ORM inserts
            kwargs["default"] = self._default
            server_default = self._server_default_clause(sa, self._default)
            if server_default is not None:
                kwargs["server_default"] = server_default
        return sa.Column(*args, **{k: v for k, v in kwargs.items() if v is not None})

    @staticmethod
    def _server_default_clause(sa: Any, value: Any) -> Any:
        """A DDL DEFAULT clause for a scalar default; None for values with no portable literal."""
        if isinstance(value, bool):
            return sa.text("TRUE") if value else sa.text("FALSE")
        if isinstance(value, (int, float)):
            return sa.text(str(value))
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return sa.text(f"'{escaped}'")
        return None


class Blueprint:
    """Collects column definitions for a table, then builds a Core ``Table``."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._columns: list[ColumnDefinition] = []
        self._indexes: list[dict[str, Any]] = []  # {using, columns, name}

    def _add(self, column: ColumnDefinition) -> ColumnDefinition:
        self._columns.append(column)
        return column

    # --- access-method indexes (btree / Postgres GIN / GiST) ---------------
    def _index_using(self, using: str, columns: tuple[str, ...], name: str | None) -> None:
        if not columns:
            raise ValueError(f"{using}_index requires at least one column")
        # sanitize non-word chars so an expression column (e.g. "name->>'en'") yields a legal index name
        slug = re.sub(r"\W+", "_", "_".join(columns)).strip("_")
        self._indexes.append(
            {
                "using": using,
                "columns": tuple(columns),
                "name": name or f"{self.name}_{slug}_{using}",
            }
        )

    def btree_index(self, *columns: str, name: str | None = None) -> None:
        """A **B-tree** index — the default access method, for composite and **expression** indexes
        (a single plain column is usually better done with ``.index()`` on the column). Expression
        columns are emitted verbatim, so a per-locale i18n lookup index is
        ``t.btree_index("name->>'en'")`` → ``CREATE INDEX ... ((name->>'en'))``. The best fit for
        exact key lookups in a ``jsonb`` column (GIN is for containment/key-existence search)."""
        self._index_using("btree", columns, name)

    def gin_index(self, *columns: str, name: str | None = None) -> None:
        """A **GIN** index on ``columns`` — the right index for ``jsonb`` containment/key lookups,
        array membership, and ``tsvector`` full-text search. Emits ``USING gin`` on Postgres; a
        plain index on other dialects (the ``postgresql_using`` kwarg is ignored there)."""
        self._index_using("gin", columns, name)

    def gist_index(self, *columns: str, name: str | None = None) -> None:
        """A **GiST** index on ``columns`` — for geometric/range types and ``tsvector`` search.
        Emits ``USING gist`` on Postgres; a plain index elsewhere."""
        self._index_using("gist", columns, name)

    def index_specs(self) -> list[dict[str, Any]]:
        """The access-method index specs (for the migrator to emit as ``create_index`` ops)."""
        return list(self._indexes)

    # --- column types (lazy sa type factories keep import light) ------------
    def id(self, name: str = "id") -> ColumnDefinition:
        import sqlalchemy as sa

        # BIGINT on Postgres/MySQL; INTEGER on SQLite (only INTEGER PRIMARY KEY autoincrements).
        def big_pk() -> Any:
            return sa.BigInteger().with_variant(sa.Integer(), "sqlite")

        return self._add(ColumnDefinition(name, big_pk, primary_key=True))

    def big_integer(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.BigInteger))

    def integer(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.Integer))

    def string(self, name: str, length: int = 255) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, lambda: sa.String(length)))

    def text(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.Text))

    def boolean(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.Boolean))

    def foreign_id(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.BigInteger))

    def timestamps(self) -> None:
        import sqlalchemy as sa

        self._add(ColumnDefinition("created_at", lambda: sa.DateTime(timezone=True)).nullable())
        self._add(ColumnDefinition("updated_at", lambda: sa.DateTime(timezone=True)).nullable())

    def float(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.Float))

    def decimal(self, name: str, precision: int = 8, scale: int = 2) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, lambda: sa.Numeric(precision, scale)))

    def date(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.Date))

    def datetime(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, lambda: sa.DateTime(timezone=True)))

    def time(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.Time))

    # --- Laravel Blueprint parity (snake_case) -------------------------------
    def timestamp(self, name: str) -> ColumnDefinition:
        """A timestamp column (Laravel ``timestamp``) — a timezone-aware DateTime."""
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, lambda: sa.DateTime(timezone=True)))

    def char(self, name: str, length: int = 255) -> ColumnDefinition:
        """A fixed-length string column (Laravel ``char``)."""
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, lambda: sa.CHAR(length)))

    def medium_text(self, name: str) -> ColumnDefinition:
        """A medium text column (Laravel ``mediumText``). Portable ``Text``; ``MEDIUMTEXT`` on MySQL."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import mysql

        return self._add(
            ColumnDefinition(name, lambda: sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"))
        )

    def long_text(self, name: str) -> ColumnDefinition:
        """A long text column (Laravel ``longText``). Portable ``Text``; ``LONGTEXT`` on MySQL."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import mysql

        return self._add(
            ColumnDefinition(name, lambda: sa.Text().with_variant(mysql.LONGTEXT(), "mysql"))
        )

    def unsigned_integer(self, name: str) -> ColumnDefinition:
        """An unsigned integer (Laravel ``unsignedInteger``). Real ``UNSIGNED`` on MySQL; a portable
        ``Integer`` on Postgres/SQLite (which have no unsigned types — matching Laravel's own fallback)."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import mysql

        return self._add(
            ColumnDefinition(
                name, lambda: sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql")
            )
        )

    def unsigned_big_integer(self, name: str) -> ColumnDefinition:
        """An unsigned big integer (Laravel ``unsignedBigInteger``) — typical for foreign keys."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import mysql

        return self._add(
            ColumnDefinition(
                name, lambda: sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql")
            )
        )

    def unsigned_small_integer(self, name: str) -> ColumnDefinition:
        """An unsigned small integer (Laravel ``unsignedSmallInteger``)."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import mysql

        return self._add(
            ColumnDefinition(
                name, lambda: sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql")
            )
        )

    def unsigned_tiny_integer(self, name: str) -> ColumnDefinition:
        """An unsigned tiny integer (Laravel ``unsignedTinyInteger``). ``SmallInteger`` portably;
        ``TINYINT UNSIGNED`` on MySQL."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import mysql

        return self._add(
            ColumnDefinition(
                name, lambda: sa.SmallInteger().with_variant(mysql.TINYINT(unsigned=True), "mysql")
            )
        )

    def json(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, sa.JSON))

    def jsonb(self, name: str) -> ColumnDefinition:
        """``JSONB`` on Postgres; portable ``JSON`` on other dialects (Core variant)."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import postgresql

        def factory() -> Any:
            return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

        return self._add(ColumnDefinition(name, factory))

    def tsvector(self, name: str) -> ColumnDefinition:
        """A Postgres ``TSVECTOR`` column for full-text search (pair with ``gin_index``);
        portable ``Text`` on other dialects. Query it with ``Builder.where_fulltext``."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import postgresql

        def factory() -> Any:
            return sa.Text().with_variant(postgresql.TSVECTOR(), "postgresql")

        return self._add(ColumnDefinition(name, factory))

    def uuid(self, name: str) -> ColumnDefinition:
        import sqlalchemy as sa

        # as_uuid=False: the Python side stays a string, matching what HasUuids generates
        return self._add(ColumnDefinition(name, lambda: sa.Uuid(as_uuid=False)))

    def enum(self, name: str, *values: str) -> ColumnDefinition:
        """Native ENUM on Postgres; SQLite degrades to VARCHAR + CHECK — both compile."""
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, lambda: sa.Enum(*values, name=f"{name}_enum")))

    def morphs(self, name: str) -> None:
        """Polymorphic columns ``{name}_id`` (BIGINT) + ``{name}_type`` (string) — the pair
        ``morph_*`` relations read (relations.py)."""
        self._add(ColumnDefinition(f"{name}_id", _big_integer_factory)).not_null()
        self.string(f"{name}_type").not_null()

    def nullable_morphs(self, name: str) -> None:
        """``morphs`` with both columns nullable (optional polymorphic owner)."""
        self._add(ColumnDefinition(f"{name}_id", _big_integer_factory)).nullable()
        self.string(f"{name}_type").nullable()

    def soft_deletes(self, name: str = "deleted_at") -> ColumnDefinition:
        """A nullable ``deleted_at`` timestamp — the SoftDeletes mixin's column."""
        import sqlalchemy as sa

        return self._add(ColumnDefinition(name, lambda: sa.DateTime(timezone=True)).nullable())

    def vector(self, name: str, dimensions: int) -> ColumnDefinition:
        """A pgvector column when the ``[vector]`` extra (``pgvector``) is installed; a portable
        JSON fallback otherwise. To actually store/query vectors on Postgres you must also enable
        the **server extension**: ``CREATE EXTENSION IF NOT EXISTS vector;`` (a migration step)."""

        def factory() -> Any:
            import importlib.util

            # loaded dynamically so static checkers don't require the untyped, optional package
            if importlib.util.find_spec("pgvector") is None:
                import sqlalchemy as sa

                return sa.JSON()
            module: Any = importlib.import_module("pgvector.sqlalchemy")
            return module.Vector(dimensions)

        return self._add(ColumnDefinition(name, factory))

    def core_columns(self) -> list[Any]:
        """Fresh, unattached Core ``Column`` objects (for Alembic ``create_table``)."""
        return [c.to_core() for c in self._columns]

    def to_table(self, metadata: Any = None) -> Any:
        import sqlalchemy as sa

        meta = metadata if metadata is not None else sa.MetaData()
        # a plain column is referenced by name; anything else becomes a text() expression index
        indexes = [
            sa.Index(
                spec["name"],
                *[c if PLAIN_IDENTIFIER.match(c) else sa.text(f"({c})") for c in spec["columns"]],
                postgresql_using=spec["using"],
            )
            for spec in self._indexes
        ]
        return sa.Table(self.name, meta, *self.core_columns(), *indexes)


def _to_sql(selectable: Any) -> str:
    if isinstance(selectable, str):
        return selectable
    return str(selectable.compile(compile_kwargs={"literal_binds": True}))


def create_view(name: str, selectable: Any) -> Any:
    """``CREATE VIEW`` over a Core ``Select`` (or raw SQL string)."""
    import sqlalchemy as sa

    return sa.text(f"CREATE VIEW {name} AS {_to_sql(selectable)}")


def create_materialized_view(name: str, selectable: Any) -> Any:
    import sqlalchemy as sa

    return sa.text(f"CREATE MATERIALIZED VIEW {name} AS {_to_sql(selectable)}")


def refresh_materialized_view(name: str, *, concurrently: bool = False) -> Any:
    import sqlalchemy as sa

    prefix = "CONCURRENTLY " if concurrently else ""
    return sa.text(f"REFRESH MATERIALIZED VIEW {prefix}{name}")


def create_extension(name: str) -> Any:
    import sqlalchemy as sa

    return sa.text(f'CREATE EXTENSION IF NOT EXISTS "{name}"')


def create_function(
    name: str,
    args: list[tuple[str, str]],
    *,
    returns: str,
    body: str,
    language: str = "plpgsql",
) -> Any:
    import sqlalchemy as sa

    arglist = ", ".join(f"{argname} {argtype}" for argname, argtype in args)
    return sa.text(
        f"CREATE OR REPLACE FUNCTION {name}({arglist}) RETURNS {returns} "
        f"LANGUAGE {language} AS $$ {body} $$"
    )


def _resolve_selectable(query: Any) -> Any:
    """A declarative ``query`` may be an arvel Builder (``.to_select()``) or a raw selectable."""
    if hasattr(query, "to_select"):
        return query.to_select()
    return query


class View:
    """Declarative read-only view (doc 08 §36). Subclass with ``name`` + ``query``;
    ``create()`` resolves to the ``create_view`` op (DR-0006)."""

    name: str
    query: Any

    def create(self) -> Any:
        return create_view(self.name, _resolve_selectable(self.query))

    def drop(self) -> Any:
        return drop_view(self.name)


class MaterializedView(View):
    """Declarative materialized view. Adds ``indexes`` and ``refresh`` (``"concurrently"``)."""

    indexes: ClassVar[list[str]] = []
    refresh: str | None = None

    def create(self) -> Any:
        return create_materialized_view(self.name, _resolve_selectable(self.query))

    def refresh_op(self) -> Any:
        return refresh_materialized_view(self.name, concurrently=self.refresh == "concurrently")

    def drop(self) -> Any:
        return drop_materialized_view(self.name)


class DatabaseFunction:
    """Declarative stored function (doc 08 §57). ``create()`` wraps the ``create_function`` op."""

    name: str
    args: ClassVar[list[tuple[str, str]]] = []
    returns: str
    language: str = "plpgsql"
    body: str

    def create(self) -> Any:
        return create_function(
            self.name,
            self.args,
            returns=self.returns,
            body=self.body,
            language=self.language,
        )


def drop_view(name: str) -> Any:
    import sqlalchemy as sa

    return sa.text(f"DROP VIEW IF EXISTS {name}")


def drop_materialized_view(name: str) -> Any:
    import sqlalchemy as sa

    return sa.text(f"DROP MATERIALIZED VIEW IF EXISTS {name}")


__all__ = [
    "Blueprint",
    "ColumnDefinition",
    "DatabaseFunction",
    "MaterializedView",
    "View",
    "create_extension",
    "create_function",
    "create_materialized_view",
    "create_view",
    "drop_materialized_view",
    "drop_view",
    "refresh_materialized_view",
]

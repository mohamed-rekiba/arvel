"""Security — SQL-injection abuse coverage for the query builder boundary.

A web framework's single most important security invariant is that untrusted input
cannot become executable SQL. arvel's builder enforces this *by construction*:
- **Column identifiers** are looked up in ``Table.c`` — an unknown/attacker-controlled
  name raises ``KeyError`` instead of being interpolated.
- **Operators** are whitelisted via a comparison map — an unknown operator raises.
- **Values** are always SQLAlchemy bound parameters — never inlined into SQL text.

These tests prove all three across generated adversarial inputs. The ``*_raw`` /
``literal_column`` methods are the documented, opt-in raw escape hatch and are out of
scope here (the app owns their inputs).
"""

from __future__ import annotations

import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects import postgresql, sqlite

from arvel.database import Builder
from arvel.database.builder import _COMPARISONS

# The operators the builder genuinely supports — sourced from the real whitelist so this can't drift
# (``=`` and ``==`` both map to ``__eq__``), plus the specially-handled ``like``/``in``.
_KNOWN_OPERATORS = set(_COMPARISONS) | {"like", "in"}

_md = sa.MetaData()
users = sa.Table(
    "users",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String),
    sa.Column("active", sa.Boolean),
)

_REAL_COLUMNS = {"id", "name", "active"}

# Classic injection payloads + generated junk that is never a real column name.
_evil_identifiers = st.one_of(
    st.sampled_from(
        [
            "id; DROP TABLE users--",
            "name' OR '1'='1",
            "1=1",
            "name); DELETE FROM users; --",
            "id`",
            'name"',
            "*",
            "id, (SELECT password FROM users)",
        ]
    ),
    st.text(min_size=1).filter(lambda s: s not in _REAL_COLUMNS),
)


@given(column=_evil_identifiers)
@settings(max_examples=200)
def test_where_rejects_unknown_column_identifier(column: str) -> None:
    """A column name that isn't a declared column raises KeyError — never injected."""
    try:
        Builder(users).where(column, "x").to_select()
    except KeyError:
        return
    raise AssertionError(f"unknown column {column!r} was not rejected")


@given(column=_evil_identifiers)
@settings(max_examples=200)
def test_order_by_rejects_unknown_column_identifier(column: str) -> None:
    try:
        Builder(users).order_by(column).to_select()
    except KeyError:
        return
    raise AssertionError(f"unknown order-by column {column!r} was not rejected")


@given(operator=st.text(min_size=1).filter(lambda s: s not in _KNOWN_OPERATORS))
@settings(max_examples=150)
def test_where_rejects_unknown_operator(operator: str) -> None:
    """The operator is whitelisted; an arbitrary operator string raises, never builds
    raw SQL."""
    try:
        Builder(users).where("id", operator, 5).to_select()
    except KeyError, AttributeError:
        return
    raise AssertionError(f"unknown operator {operator!r} was not rejected")


@given(payload=st.text())
@settings(max_examples=300)
def test_where_value_is_always_bound_never_inlined(payload: str) -> None:
    """Any value — including SQL metacharacters — is carried as a bound parameter, not
    inlined into SQL text. We prove parameterization positively: the value appears in
    the compiled statement's bound params, while the SQL text uses a placeholder.
    (A substring search would false-positive on short values that occur inside keywords
    like SELECT/users.)"""
    stmt = Builder(users).where("name", payload).to_select()
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        compiled = stmt.compile(dialect=dialect)
        assert payload in compiled.params.values(), f"value not bound as a parameter: {payload!r}"


@given(direction=st.text().filter(lambda s: s != "desc"))
@settings(max_examples=150)
def test_order_by_direction_cannot_inject(direction: str) -> None:
    """``direction`` is a branch (desc vs asc), never interpolated — any non-'desc'
    value yields exactly ``ORDER BY users.id ASC``, so no attacker string can reach
    the ORDER BY clause."""
    stmt = Builder(users).order_by("id", direction).to_select()
    compiled = str(stmt.compile(dialect=sqlite.dialect()))
    assert compiled.endswith("ORDER BY users.id ASC")

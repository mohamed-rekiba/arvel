"""Advanced DB (doc 08) — db.call_function statement fidelity (D7, unit half).

The integration half (a real plpgsql function on Postgres) lives in
tests/integration/test_postgres_call_function.py.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql, sqlite

from arvel.database import ConnectionResolver


def test_call_function_builds_core_select_not_raw_sql() -> None:
    stmt = ConnectionResolver.call_function_statement("increment_balance", 7, 100)
    pg = str(stmt.compile(dialect=postgresql.dialect()))
    lite = str(stmt.compile(dialect=sqlite.dialect()))
    # Core SELECT over the func registry (injection-safe), compiles multi-dialect
    assert "increment_balance" in pg
    assert "SELECT" in pg.upper()
    assert "increment_balance" in lite


def test_call_function_passes_kwargs_in_order() -> None:
    stmt = ConnectionResolver.call_function_statement("f", account_id=7, amount=100)
    compiled = str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert compiled.index("7") < compiled.index("100")  # kwargs preserve declared order

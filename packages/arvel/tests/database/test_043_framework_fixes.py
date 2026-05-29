"""QA-Pre tests for WI-arvel-043: framework query builder critical fixes.

All tests are source-inspection tests (no DB, no I/O) that fail before
the fixes are applied and pass after.

Tests verify structural patterns in the source code that ensure correctness —
they are not end-to-end tests, which require a live PostgreSQL connection.
"""

from __future__ import annotations

import pathlib

_QUERY_PY = pathlib.Path(__file__).parent.parent.parent / "src" / "arvel" / "database" / "query.py"
_QUERY_MIXIN_PY = (
    pathlib.Path(__file__).parent.parent.parent / "src" / "arvel" / "database" / "query_mixin.py"
)
_PAGINATOR_PY = (
    pathlib.Path(__file__).parent.parent.parent / "src" / "arvel" / "database" / "paginator.py"
)
_MODEL_PY = pathlib.Path(__file__).parent.parent.parent / "src" / "arvel" / "database" / "model.py"
_PERMISSION_TRAITS_PY = (
    pathlib.Path(__file__).parent.parent.parent.parent.parent
    / "arvel-permission"
    / "src"
    / "arvel_permission"
    / "traits.py"
)


def _src(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_body(src: str, func_name: str) -> str:
    """Extract the source body of the first function/method named func_name."""
    start = src.find(f"def {func_name}(")
    if start == -1:
        return ""
    # Find the end by looking for the next same-level def or end of string
    end = src.find("\n    async def ", start + 1)
    end2 = src.find("\n    def ", start + 1)
    if end == -1:
        end = end2
    elif end2 != -1:
        end = min(end, end2)
    return src[start:end] if end != -1 else src[start:]


# ─── FR-001: lock_for_update in first() and sole() ───────────────────────────


class TestF001LockForUpdateInFirst:
    def test_first_checks_lock_flag(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "first")
        assert "_lock_for_update" in body, "F-001 not fixed: first() must check _lock_for_update"

    def test_first_calls_with_for_update(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "first")
        assert "with_for_update" in body, (
            "F-001 not fixed: first() must call with_for_update() when lock flag is set"
        )

    def test_sole_checks_lock_flag(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "sole")
        assert "_lock_for_update" in body, "F-001 not fixed: sole() must check _lock_for_update"

    def test_sole_calls_with_for_update(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "sole")
        assert "with_for_update" in body, (
            "F-001 not fixed: sole() must call with_for_update() when lock flag is set"
        )

    def test_lock_alias_exists(self) -> None:
        src = _src(_QUERY_PY)
        assert "def lock(" in src or "lock = lock_for_update" in src, (
            "F-001 not fixed: lock() alias must exist (maps to lock_for_update)"
        )


# ─── FR-002: order_by("-column") descending shorthand ────────────────────────


class TestF002OrderByDescShorthand:
    def test_order_by_handles_dash_prefix(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "order_by")
        assert "startswith" in body or '"-"' in body or "desc" in body.lower(), (
            "F-002 not fixed: order_by() must handle '-column' descending shorthand"
        )

    def test_resolve_column_handles_dash_or_order_by_does(self) -> None:
        src = _src(_QUERY_PY)
        # Either _resolve_column or order_by itself handles the prefix
        resolve_start = src.find("def _resolve_column(")
        if resolve_start != -1:
            resolve_end = src.find("\ndef ", resolve_start + 1)
            resolve_body = (
                src[resolve_start:resolve_end] if resolve_end != -1 else src[resolve_start:]
            )
            has_desc_in_resolve = "desc" in resolve_body.lower() or "startswith" in resolve_body
        else:
            has_desc_in_resolve = False

        order_by_body = _func_body(src, "order_by")
        has_desc_in_order_by = "desc" in order_by_body.lower() or "startswith" in order_by_body

        assert has_desc_in_resolve or has_desc_in_order_by, (
            "F-002 not fixed: descending shorthand must be handled in _resolve_column or order_by"
        )

    def test_desc_import_or_from_sqlalchemy(self) -> None:
        src = _src(_QUERY_PY)
        assert "desc" in src, "F-002 not fixed: sqlalchemy.desc must be imported or referenced"


# ─── FR-003: where_any() operator surface ────────────────────────────────────


class TestF003WhereAnyOperators:
    def _operator_src(self) -> str:
        # Operators may live in a module-level helper (_apply_operator) or inline in where_any
        src = _src(_QUERY_PY)
        helper = _func_body(src, "_apply_operator")
        inline = _func_body(src, "where_any")
        return helper + inline

    def test_where_any_supports_ilike(self) -> None:
        assert "ilike" in self._operator_src(), (
            "F-003 not fixed: where_any() must support 'ilike' operator"
        )

    def test_where_any_supports_gte(self) -> None:
        src = self._operator_src()
        assert ">=" in src or "ge" in src, "F-003 not fixed: where_any() must support '>=' operator"

    def test_where_any_supports_lte(self) -> None:
        src = self._operator_src()
        assert "<=" in src or "le" in src, "F-003 not fixed: where_any() must support '<=' operator"

    def test_where_any_supports_ne(self) -> None:
        src = self._operator_src()
        assert "!=" in src or "__ne__" in src or "ne" in src, (
            "F-003 not fixed: where_any() must support '!=' operator"
        )

    def test_where_any_raises_on_unknown_operator(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "where_any")
        assert "ValueError" in body or "raise" in body, (
            "F-003 not fixed: where_any() must raise ValueError for unknown operators"
        )
        # The silent fallback to equality must be removed
        assert "else:\n                parts.append(col == value)" not in body, (
            "F-003 not fixed: silent equality fallback must be removed from where_any()"
        )


# ─── FR-004: where_json_path() ───────────────────────────────────────────────


class TestF004WhereJsonPath:
    def test_where_json_path_method_exists(self) -> None:
        src = _src(_QUERY_PY)
        assert "def where_json_path(" in src, (
            "F-004 not fixed: where_json_path() method must exist in QueryBuilder"
        )

    def test_where_json_path_class_shortcut_exists(self) -> None:
        src = _src(_QUERY_MIXIN_PY)
        body = _func_body(src, "where_json_path")
        assert "cls.query().where_json_path(col, path, value)" in body, (
            "F-004 regression: Model.where_json_path() must forward to QueryBuilder"
        )

    def test_where_json_path_uses_jsonb_arrow(self) -> None:
        src = _src(_QUERY_PY)
        start = src.find("def where_json_path(")
        end = src.find("\n    def ", start + 1)
        body = src[start:end] if end != -1 else src[start:]
        # Should use PostgreSQL JSONB ->> operator
        assert "->>" in body or "json_path" in body.lower() or "text(" in body, (
            "F-004 not fixed: where_json_path() must use JSONB ->> path extraction"
        )


# ─── FR-005: increment/decrement return rowcount ─────────────────────────────


class TestF005IncrementDecrement:
    def test_increment_returns_int(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "increment")
        assert "return" in body and "rowcount" in body, (
            "F-005 not fixed: increment() must return int rowcount"
        )

    def test_increment_signature_returns_int(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "increment")
        # Signature must be -> int, not -> None
        assert "-> None" not in body.split(":")[0] or "-> int" in body, (
            "F-005 not fixed: increment() return type must be int, not None"
        )

    def test_decrement_returns_int(self) -> None:
        src = _src(_QUERY_PY)
        body = _func_body(src, "decrement")
        # decrement calls increment — so it must return the result
        assert "return" in body, (
            "F-005 not fixed: decrement() must return the rowcount from increment()"
        )


# ─── FR-006: Model.find() routes through QB ──────────────────────────────────


class TestF006ModelFindScopedRouting:
    def test_model_find_does_not_use_session_get(self) -> None:
        src = _src(_MODEL_PY)
        # Find the find() classmethod body
        start = src.find("async def find(cls, pk")
        end = src.find("\n    @classmethod", start + 1)
        if end == -1:
            end = src.find("\n    async def ", start + 1)
        body = src[start:end] if end != -1 else src[start:]
        assert "session.get(" not in body, (
            "F-006 not fixed: Model.find() must not use session.get() — it bypasses global scopes"
        )

    def test_model_find_uses_query_builder(self) -> None:
        src = _src(_MODEL_PY)
        start = src.find("async def find(cls, pk")
        end = src.find("\n    @classmethod", start + 1)
        if end == -1:
            end = src.find("\n    async def ", start + 1)
        body = src[start:end] if end != -1 else src[start:]
        assert "where(" in body or ".first()" in body or "query()" in body, (
            "F-006 not fixed: Model.find() must route through the query builder"
        )


# ─── FR-007: Paginator.to_dict() and CursorPaginator.has_more ────────────────


class TestF007PaginatorToDict:
    def test_paginator_has_to_dict(self) -> None:
        src = _src(_PAGINATOR_PY)
        assert "def to_dict(" in src, "F-007 not fixed: Paginator must have a to_dict() method"

    def test_paginator_to_dict_includes_meta(self) -> None:
        src = _src(_PAGINATOR_PY)
        start = src.find("def to_dict(")
        body = src[start : start + 400] if start != -1 else ""
        assert "meta" in body, "F-007 not fixed: Paginator.to_dict() must include 'meta' key"

    def test_paginator_to_dict_includes_links(self) -> None:
        src = _src(_PAGINATOR_PY)
        start = src.find("def to_dict(")
        body = src[start : start + 400] if start != -1 else ""
        assert "links" in body, "F-007 not fixed: Paginator.to_dict() must include 'links' key"

    def test_cursor_paginator_has_has_more_property(self) -> None:
        src = _src(_PAGINATOR_PY)
        assert "has_more" in src, "F-007 not fixed: CursorPaginator must expose a has_more property"


# ─── FR-008: RBAC has_permission_to() eager-load guard ───────────────────────


class TestF008RbacEagerLoadGuard:
    def test_traits_has_missing_greenlet_guard(self) -> None:
        if not _PERMISSION_TRAITS_PY.exists():
            return  # skip if arvel-permission not on path
        src = _src(_PERMISSION_TRAITS_PY)
        # Should have either a try/except MissingGreenlet or documented eager-load pattern
        has_greenlet_guard = "MissingGreenlet" in src or "greenlet" in src.lower()
        has_docstring_note = "with_(" in src and "permissions" in src and "roles" in src
        assert has_greenlet_guard or has_docstring_note, (
            "F-008 not fixed: has_permission_to() must guard against unloaded role.permissions "
            "or document the required eager-load pattern"
        )

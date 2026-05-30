"""QA-Pre tests for WI-arvel-044 framework fixes.

Source-inspection style (no live DB) — checks that the implementation
matches the patterns required by PRD-044 ACs. All tests must FAIL before
the implementation and PASS after.
"""

from __future__ import annotations

import inspect

# ── helpers ────────────────────────────────────────────────────────────────────


def _src(module_path: str) -> str:
    import importlib

    mod = importlib.import_module(module_path)
    return inspect.getsource(mod)


def _extract_method(src: str, method_sig: str) -> str:
    """Return source lines of the first method matching method_sig."""
    lines = src.splitlines()
    out = ""
    in_method = False
    for line in lines:
        if method_sig in line:
            in_method = True
        if in_method:
            out += line + "\n"
            stripped = line.strip()
            is_end = stripped.startswith(("async def", "def "))
            if is_end and method_sig not in line and out.count("\n") > 2:
                break
    return out


def _extract_class(src: str, class_name: str) -> str:
    """Return source lines from class_name up to the next top-level class."""
    lines = src.splitlines()
    out = ""
    in_cls = False
    for line in lines:
        if f"class {class_name}(" in line:
            in_cls = True
        if in_cls:
            out += line + "\n"
            seen_another = line.strip().startswith("class ") and class_name not in line
            if seen_another and out.count("class ") > 1:
                break
    return out


# ── FR-001: Authenticate uses AuthManager (F-009 + F-016) ─────────────────────


class TestAuthenticateUsesAuthManager:
    """AC-001a/b/c/d: Authenticate must resolve AuthManager, not Guard."""

    def test_authenticate_imports_auth_manager(self) -> None:
        """Authenticate should import or reference AuthManager."""
        src = _src("arvel.http._middleware_core")
        assert "AuthManager" in src, (
            "F-009/F-016: Authenticate does not reference AuthManager. "
            "Must use container.make(AuthManager).guard(self._guard_name)."
        )

    def test_authenticate_does_not_make_guard_directly(self) -> None:
        """container.make(Guard) bypasses guard_name — must be removed."""
        src = _src("arvel.http._middleware_core")
        assert "container.make(Guard)" not in src, (
            "F-009/F-016: Authenticate still calls container.make(Guard). "
            "Replace with container.make(AuthManager).guard(self._guard_name)."
        )

    def test_authenticate_calls_manager_guard(self) -> None:
        """guard(self._guard_name) must be called on the manager."""
        src = _src("arvel.http._middleware_core")
        assert ".guard(" in src and "AuthManager" in src, (
            "F-009/F-016: Authenticate must call AuthManager.guard(self._guard_name)."
        )


# ── FR-002: QueryBuilder.find() respects global scopes (F-012) ─────────────────


class TestQueryBuilderFindUsesScopes:
    """AC-002a/b/c: QueryBuilder.find() must not call session.get()."""

    def test_query_builder_find_no_session_get(self) -> None:
        """session.get() bypasses scopes — must be replaced with scoped QB."""
        src = _src("arvel.database.query")
        lines = src.splitlines()
        in_find = False
        for line in lines:
            if "async def find(self, pk" in line:
                in_find = True
            if in_find:
                stripped = line.strip()
                is_comment = stripped.startswith("#")
                if not is_comment and "session.get(" in line:
                    raise AssertionError(
                        f"F-012: QueryBuilder.find() calls session.get() in code: {line!r}. "
                        "Must route through the scoped query builder."
                    )
                if stripped == "" or (stripped.startswith("async def") and "find" not in stripped):
                    break

    def test_query_builder_find_uses_where(self) -> None:
        """find() should apply a where clause on the PK for scope compatibility."""
        find_src = _extract_method(_src("arvel.database.query"), "async def find(self, pk")
        assert ".first()" in find_src or "first()" in find_src, (
            "F-012: QueryBuilder.find() must call .first() after a scoped where clause."
        )


# ── FR-004: CursorPaginator.to_dict() + SimplePaginator.to_dict() (F-029) ──────


class TestPaginatorToDictMethods:
    """AC-004a/b/c: Both paginator types must have to_dict()."""

    def test_cursor_paginator_has_to_dict(self) -> None:
        """CursorPaginator must expose to_dict()."""
        cursor_src = _extract_class(_src("arvel.database.query"), "CursorPaginator")
        assert "def to_dict" in cursor_src, (
            "F-029: CursorPaginator is missing to_dict(). "
            "Must return {data, meta, links} with links.next = next_cursor."
        )

    def test_simple_paginator_has_to_dict(self) -> None:
        """SimplePaginator must expose to_dict()."""
        simple_src = _extract_class(_src("arvel.database.query"), "SimplePaginator")
        assert "def to_dict" in simple_src, (
            "F-029: SimplePaginator is missing to_dict(). "
            "Must return {data, meta, links} with meta.total = None."
        )

    def test_cursor_paginator_to_dict_returns_next_cursor(self) -> None:
        """CursorPaginator.to_dict() must include next_cursor in links."""
        cursor_src = _extract_class(_src("arvel.database.query"), "CursorPaginator")
        assert "next_cursor" in cursor_src and "to_dict" in cursor_src, (
            "F-029: CursorPaginator.to_dict() must expose next_cursor in links."
        )


# ── FR-005: Model.save() fires correct events (F-035) ──────────────────────────


class TestModelSaveFiresCorrectEvents:
    """AC-005a/b/c/d: save() must fire 'created' for new and 'updated' for existing."""

    def test_model_save_detects_pending(self) -> None:
        """save() must check inspect().pending before choosing event."""
        save_src = _extract_method(_src("arvel.database.model"), "async def save(self)")
        assert "pending" in save_src, (
            "F-035: Model.save() must check inspect(self).pending to detect new vs existing rows."
        )

    def test_model_save_fires_created_event(self) -> None:
        """save() must fire 'created' for new instances."""
        src = _src("arvel.database.model")
        assert '"created"' in src or "'created'" in src, (
            "F-035: Model.save() must fire the 'created' event for new model instances."
        )

    def test_model_save_fires_updated_event(self) -> None:
        """save() must fire 'updated' for existing instances."""
        src = _src("arvel.database.model")
        assert '"updated"' in src or "'updated'" in src, (
            "F-035: Model.save() must fire the 'updated' event for persistent model instances."
        )


# ── FR-006: Model.fresh() uses query builder (F-036) ───────────────────────────


class TestModelFreshUsesQueryBuilder:
    """AC-006a/b: fresh() must route through the scoped query builder."""

    def test_model_fresh_no_raw_select(self) -> None:
        """fresh() must not build a raw select() statement."""
        fresh_src = _extract_method(_src("arvel.database.model"), "async def fresh(self)")
        assert "select(" not in fresh_src or "query()" in fresh_src, (
            "F-036: Model.fresh() must route through type(self).query() instead of raw select()."
        )

    def test_model_fresh_calls_query(self) -> None:
        """fresh() should call .query() to pick up global scopes."""
        fresh_src = _extract_method(_src("arvel.database.model"), "async def fresh(self)")
        assert ".query()" in fresh_src or "query()" in fresh_src, (
            "F-036: Model.fresh() must use type(self).query() to apply global scopes."
        )

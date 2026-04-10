"""Fluent query builder over SQLAlchemy select().

Wraps a SA Select statement with chainable methods for filtering,
ordering, pagination, eager loading, relationship queries, and
recursive CTEs. All parameters are bound via SA's expression engine —
zero string interpolation.
"""

from __future__ import annotations

import os
import warnings
from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import Table, func, literal_column, select
from sqlalchemy.orm import DeclarativeBase, selectinload

from arvel.data.collection import ArvelCollection
from arvel.data.results import TreeNode, WithCount
from arvel.logging import Log

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import Column, Select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import RelationshipProperty
    from sqlalchemy.sql._typing import _ColumnExpressionOrStrLabelArgument
    from sqlalchemy.sql.elements import ColumnElement

    from arvel.data.relationships.descriptors import ComparisonOperator

_VALID_OPERATORS: frozenset[str] = frozenset({">", ">=", "<", "<=", "=", "!="})
_logger = Log.named("arvel.data.query")


class QueryBuilder[T: DeclarativeBase]:
    """Fluent query builder producing parameterized SQL.

    Usage::

        users = await User.query(session).where(User.active == True).order_by(User.name).all()
    """

    DEFAULT_MAX_DEPTH: int = 100

    def __init__(
        self, model_cls: type[T], session: AsyncSession, *, owns_session: bool = False
    ) -> None:
        self._model_cls = model_cls
        self._session = session
        self._owns_session = owns_session
        self._stmt: Select[tuple[T]] = select(model_cls)
        self._count_subqueries: list[tuple[str, Any]] = []
        self._has_order_by = False
        self._excluded_global_scopes: set[str] = set()
        self._global_scopes_applied = False

    async def _release_session(self) -> None:
        """Close the session if this query builder created it."""
        if self._owns_session:
            await self._session.close()

    @property
    def _table(self) -> Table:
        """Narrow __table__ from FromClause to Table for column/name access."""
        table = self._model_cls.__table__
        if not isinstance(table, Table):
            msg = f"{self._model_cls.__name__}.__table__ is not a Table"
            raise TypeError(msg)
        return table

    def where(self, *criteria: ColumnElement[bool]) -> Self:
        self._stmt = self._stmt.where(*criteria)
        return self

    def order_by(self, *columns: _ColumnExpressionOrStrLabelArgument[Any]) -> Self:
        self._stmt = self._stmt.order_by(*columns)
        self._has_order_by = True
        return self

    def limit(self, n: int) -> Self:
        self._stmt = self._stmt.limit(n)
        return self

    def offset(self, n: int) -> Self:
        self._stmt = self._stmt.offset(n)
        return self

    # ------------------------------------------------------------------
    # Scope support
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Resolve local query scopes defined on the model."""
        registry: Any = getattr(self._model_cls, "__scope_registry__", None)
        if registry is not None:
            scope_fn = registry.get_local(name)
            if scope_fn is not None:

                def _call_scope(*args: Any, **kwargs: Any) -> Self:  # type: ignore[type-var]
                    return scope_fn(self, *args, **kwargs)

                return _call_scope
        msg = f"'{type(self).__name__}' has no attribute {name!r}"
        raise AttributeError(msg)

    def without_global_scope(self, scope_name: str) -> Self:
        """Exclude a named global scope from this query."""
        self._excluded_global_scopes.add(scope_name)
        return self

    def without_global_scopes(self) -> Self:
        """Exclude all global scopes from this query."""
        self._exclude_all_global_scopes = True
        return self

    def with_trashed(self) -> Self:
        """Include soft-deleted rows (removes the SoftDeleteScope)."""
        return self.without_global_scope("SoftDeleteScope")

    def only_trashed(self) -> Self:
        """Return only soft-deleted rows."""
        self.without_global_scope("SoftDeleteScope")
        from arvel.data.soft_deletes import is_soft_deletable

        if is_soft_deletable(self._model_cls):
            deleted_at_col = getattr(self._model_cls, "deleted_at")  # noqa: B009  # dynamic: SoftDeletes mixin adds this column
            self._stmt = self._stmt.where(deleted_at_col.isnot(None))
        return self

    def _apply_global_scopes(self) -> None:
        """Apply all non-excluded global scopes to the statement."""
        if self._global_scopes_applied:
            return
        self._global_scopes_applied = True

        registry: Any = getattr(self._model_cls, "__scope_registry__", None)
        if registry is None:
            return

        exclude_all = getattr(self, "_exclude_all_global_scopes", False)
        for gs in registry.get_globals():
            if exclude_all:
                continue
            if gs.name in self._excluded_global_scopes:
                continue
            gs.apply(self)

    def _get_rel_attr(self, relationship_name: str) -> RelationshipProperty[Any]:
        """Resolve a relationship attribute by name, raising on invalid names."""
        rel_attr = getattr(self._model_cls, relationship_name, None)
        if rel_attr is None:
            msg = (
                f"'{self._model_cls.__name__}' has no relationship '{relationship_name}'. "
                f"Declared relationships: {list(self._get_declared_names())}"
            )
            raise ValueError(msg)
        return rel_attr

    def _get_declared_names(self) -> set[str]:
        """Return the set of declared relationship names on the model."""
        registry = getattr(self._model_cls, "__relationship_registry__", None)
        if registry is not None:
            return set(registry.all().keys())
        return set()

    def with_(self, *relationships: str) -> Self:
        """Eager-load relationships by name using selectinload.

        Supports nested dot notation: ``with_("posts", "posts.comments")``
        produces ``selectinload(Model.posts).selectinload(Post.comments)``.

        Raises ValueError if a relationship name does not exist on the model.
        """
        for rel_path in relationships:
            parts = rel_path.split(".")
            loader = self._build_nested_loader(parts)
            self._stmt = self._stmt.options(loader)
        return self

    def _build_nested_loader(self, parts: list[str]) -> Any:
        """Walk a dotted path and chain selectinload() calls.

        Raises ValueError if any segment in the path is not a valid relationship.
        """
        current_cls = self._model_cls
        loader = None

        for part in parts:
            attr = getattr(current_cls, part, None)
            if attr is None:
                msg = (
                    f"'{current_cls.__name__}' has no attribute '{part}' "
                    f"(from path '{'.'.join(parts)}')"
                )
                raise ValueError(msg)

            loader = selectinload(attr) if loader is None else loader.selectinload(attr)

            prop = getattr(attr, "property", None)
            if prop is not None and hasattr(prop, "mapper"):
                current_cls = prop.mapper.class_
            else:
                break

        return loader

    def has(
        self,
        relationship_name: str,
        operator: ComparisonOperator = ">",
        count: int = 0,
    ) -> Self:
        """Filter to models that have related records matching a count condition.

        Raises ValueError if the relationship name doesn't exist.

        Examples::

            User.query(s).has("posts").all()          # users with >=1 post
            User.query(s).has("posts", ">", 5).all()  # users with >5 posts
        """
        rel_attr = self._get_rel_attr(relationship_name)
        subq = self._relationship_count_subquery(rel_attr)
        condition = self._count_condition(subq, operator, count)
        self._stmt = self._stmt.where(condition)
        return self

    def doesnt_have(self, relationship_name: str) -> Self:
        """Filter to models that have zero related records."""
        return self.has(relationship_name, "=", 0)

    def where_has(
        self,
        relationship_name: str,
        callback: Callable[..., ColumnElement[bool]],
    ) -> Self:
        """Filter to models whose related records match extra conditions.

        Raises ValueError if the relationship name doesn't exist.

        The callback receives the related model class and should return
        a SQLAlchemy criterion::

            User.query(s).where_has("posts", lambda Post: Post.is_published == True).all()
        """
        rel_attr = self._get_rel_attr(relationship_name)

        prop = rel_attr.property
        related_cls = prop.mapper.class_
        related_table = related_cls.__table__

        local_pk = self._table.c.id
        fk_col = self._find_fk_column(prop, related_table)
        if fk_col is None:
            msg = (
                f"Cannot resolve FK for relationship '{relationship_name}' "
                f"between '{self._model_cls.__name__}' and '{related_cls.__name__}'"
            )
            raise ValueError(msg)

        extra_condition = callback(related_cls)
        subq = (
            select(func.count())
            .select_from(related_table)
            .where(fk_col == local_pk)
            .where(extra_condition)
            .correlate(self._model_cls)
            .scalar_subquery()
        )
        self._stmt = self._stmt.where(subq > 0)
        return self

    def with_count(self, relationship_name: str) -> Self:
        """Add a ``{relationship}_count`` column to the result.

        The count is computed as a correlated subquery.
        Supports both direct FK relationships and M2M (pivot/secondary) relationships.

        Raises ValueError if the relationship name doesn't exist.
        """
        rel_attr = self._get_rel_attr(relationship_name)
        subq = self._relationship_count_subquery(rel_attr)
        label = f"{relationship_name}_count"
        self._stmt = self._stmt.add_columns(subq.label(label))
        self._count_subqueries.append((label, subq))
        return self

    def _relationship_count_subquery(self, rel_attr: Any) -> Any:
        """Build a correlated COUNT subquery for a relationship property.

        Handles both direct FK and M2M (secondary table) relationships.
        """
        prop = rel_attr.property
        related_cls = prop.mapper.class_
        related_table = related_cls.__table__

        local_pk = self._table.c.id

        if hasattr(prop, "secondary") and prop.secondary is not None:
            return self._m2m_count_subquery(prop.secondary, local_pk)

        fk_col = self._find_fk_column(prop, related_table)
        if fk_col is None:
            return select(func.literal(0)).scalar_subquery()

        return (
            select(func.count())
            .select_from(related_table)
            .where(fk_col == local_pk)
            .correlate(self._model_cls)
            .scalar_subquery()
        )

    def _m2m_count_subquery(self, secondary: Table, local_pk: Column[Any]) -> Any:
        """Build a COUNT subquery for M2M relationships via the pivot table.

        Finds the FK column on the secondary table that references the owner table.
        """
        owner_table_name = self._table.name
        owner_fk_col: Column[Any] | None = None

        for col in secondary.columns:
            for fk in col.foreign_keys:
                if fk.column.table.name == owner_table_name:
                    owner_fk_col = col
                    break
            if owner_fk_col is not None:
                break

        if owner_fk_col is None:
            return select(func.literal(0)).scalar_subquery()

        return (
            select(func.count())
            .select_from(secondary)
            .where(owner_fk_col == local_pk)
            .correlate(self._model_cls)
            .scalar_subquery()
        )

    @staticmethod
    def _find_fk_column(prop: Any, related_table: Any) -> Column[Any] | None:
        """Find the FK column on the related table that points back to the owner."""
        if hasattr(prop, "secondary") and prop.secondary is not None:
            return None

        for pair in prop.local_remote_pairs:
            _local_col, remote_col = pair
            for col in related_table.columns:
                if col.name == remote_col.name:
                    return col
        return None

    @staticmethod
    def _count_condition(
        subq: Any, operator: ComparisonOperator, count: int
    ) -> ColumnElement[bool]:
        ops: dict[str, Callable[[Any, int], ColumnElement[bool]]] = {
            ">": lambda s, c: s > c,
            ">=": lambda s, c: s >= c,
            "<": lambda s, c: s < c,
            "<=": lambda s, c: s <= c,
            "=": lambda s, c: s == c,
            "!=": lambda s, c: s != c,
        }
        op_fn = ops.get(operator)
        if op_fn is None:
            valid = ", ".join(sorted(_VALID_OPERATORS))
            msg = f"Unsupported comparison operator. Valid operators: {valid}"
            raise ValueError(msg)
        return op_fn(subq, count)

    def recursive(
        self,
        anchor: Any,
        step: Callable[..., Any],
        *,
        max_depth: int | None = None,
        cycle_detection: bool = False,
    ) -> RecursiveQueryBuilder[T]:
        """Build a WITH RECURSIVE CTE from anchor and step conditions.

        Returns a ``RecursiveQueryBuilder`` whose ``all()`` / ``first()``
        produce ``TreeNode[T]`` results instead of plain ``T``.

        Args:
            anchor: WHERE clause for the anchor (base case) rows.
            step: Callable receiving the CTE alias and returning the join condition
                  for the recursive term.
            max_depth: Maximum recursion depth (default DEFAULT_MAX_DEPTH).
            cycle_detection: If True, add path-tracking to detect cycles.
        """
        rqb = RecursiveQueryBuilder(self._model_cls, self._session, owns_session=self._owns_session)
        rqb._stmt = self._stmt
        rqb._has_order_by = self._has_order_by
        rqb._excluded_global_scopes = self._excluded_global_scopes
        rqb._global_scopes_applied = self._global_scopes_applied

        if max_depth is None:
            max_depth = self.DEFAULT_MAX_DEPTH

        table = rqb._table
        cols = [c.label(c.name) for c in table.columns]

        anchor_stmt = select(*cols, literal_column("0").label("depth")).where(anchor)
        cte = anchor_stmt.cte(name="tree", recursive=True)

        step_condition = step(cte)
        recursive_cols = [table.c[c.name].label(c.name) for c in table.columns]
        recursive_stmt = (
            select(*recursive_cols, (cte.c.depth + 1).label("depth"))
            .select_from(table.join(cte, step_condition))
            .where(cte.c.depth < max_depth)
        )

        full_cte = cte.union_all(recursive_stmt)
        rqb._stmt = select(full_cte)

        try:
            parent_col, id_col = rqb._find_self_ref_columns()
            rqb._recursive_id_key = id_col.name
            rqb._recursive_parent_key = parent_col.name
        except ValueError:
            pass

        return rqb

    def ancestors(
        self, node_id: int | str, *, max_depth: int | None = None
    ) -> RecursiveQueryBuilder[T]:
        """Return all ancestors of node_id up to the root.

        Auto-detects the parent_id column from self-referencing FK.
        """
        parent_col, id_col = self._find_self_ref_columns()

        rqb = self.recursive(
            anchor=id_col == node_id,
            step=lambda tree: id_col == tree.c[parent_col.name],
            max_depth=max_depth,
        )
        rqb._recursive_id_key = id_col.name
        rqb._recursive_parent_key = parent_col.name
        return rqb._exclude_anchor_row(node_id, id_col)

    def descendants(
        self, node_id: int | str, *, max_depth: int | None = None
    ) -> RecursiveQueryBuilder[T]:
        """Return all descendants of node_id down to the leaves.

        Auto-detects the parent_id column from self-referencing FK.
        """
        parent_col, id_col = self._find_self_ref_columns()

        rqb = self.recursive(
            anchor=id_col == node_id,
            step=lambda tree: parent_col == tree.c[id_col.name],
            max_depth=max_depth,
        )
        rqb._recursive_id_key = id_col.name
        rqb._recursive_parent_key = parent_col.name
        return rqb._exclude_anchor_row(node_id, id_col)

    def _find_self_ref_columns(self) -> tuple[Column[Any], Column[Any]]:
        """Find the parent_id FK column and the id PK column."""
        table = self._table

        pk_col: Column[Any] | None = None
        parent_col: Column[Any] | None = None
        for col in table.columns:
            if col.primary_key:
                pk_col = col
            for fk in col.foreign_keys:
                if fk.column.table is table:
                    parent_col = col
                    break

        if pk_col is None:
            msg = f"No primary key found on {table.name}"
            raise ValueError(msg)
        if parent_col is None:
            msg = f"No self-referencing FK found on {table.name}"
            raise ValueError(msg)
        return parent_col, pk_col

    def build_statement(self) -> Select[tuple[T]]:
        """Return the underlying SA Select for inspection/testing."""
        return self._stmt

    async def all(self) -> ArvelCollection[T]:
        """Execute the query and return all results."""
        try:
            self._apply_global_scopes()
            result = await self._session.execute(self._stmt)
            if self._count_subqueries:
                return ArvelCollection(row[0] for row in result.all())
            return ArvelCollection(result.scalars().all())
        finally:
            await self._release_session()

    async def first(self) -> T | None:
        """Execute the query and return the first result, or ``None``."""
        if not self._has_order_by:
            warnings.warn(
                f"QueryBuilder[{self._model_cls.__name__}].first() called without order_by() "
                f"— results may be non-deterministic",
                stacklevel=2,
            )
        try:
            self._apply_global_scopes()
            result = await self._session.execute(self._stmt)
            if self._count_subqueries:
                row = result.first()
                return row[0] if row is not None else None
            return result.scalars().first()
        finally:
            await self._release_session()

    async def all_with_counts(self) -> list[WithCount[T]]:
        """Execute a ``with_count()`` query and return typed results.

        Each result wraps the model instance with relationship counts::

            results = await User.query(s).with_count("posts").all_with_counts()
            for r in results:
                print(r.instance.name, r.counts["posts"])
        """
        try:
            self._apply_global_scopes()
            result = await self._session.execute(self._stmt)
            return self._build_with_counts(list(result.all()))
        finally:
            await self._release_session()

    async def first_with_count(self) -> WithCount[T] | None:
        """Execute a ``with_count()`` query and return the first typed result."""
        try:
            self._apply_global_scopes()
            result = await self._session.execute(self._stmt)
            row = result.first()
            if row is None:
                return None
            return self._build_with_counts([row])[0]
        finally:
            await self._release_session()

    def _build_with_counts(self, rows: list[Any]) -> list[WithCount[T]]:
        """Wrap composite rows into ``WithCount[T]`` instances."""
        results: list[WithCount[T]] = []
        for row in rows:
            instance = row[0]
            counts: dict[str, int] = {}
            for i, (label, _subq) in enumerate(self._count_subqueries, start=1):
                rel_name = label.removesuffix("_count")
                counts[rel_name] = int(row[i])
            results.append(WithCount(instance=instance, counts=counts))
        return results

    def _get_column_names(self) -> list[str]:
        """Return the column names of the model table (excluding the CTE depth column)."""
        return [col.name for col in self._table.columns]

    def to_sql(self) -> str:
        """Return the compiled SQL string for debugging.

        Disabled in production (``ARVEL_DEBUG`` must be ``true``).
        Raises ``RuntimeError`` if called with debug mode off.
        """
        debug = os.environ.get("ARVEL_DEBUG", "").lower() in ("1", "true", "yes")
        if not debug:
            msg = "to_sql() requires ARVEL_DEBUG=true"
            raise RuntimeError(msg)
        return str(self._stmt.compile(compile_kwargs={"literal_binds": True}))

    def __repr__(self) -> str:
        return f"QueryBuilder({self._model_cls.__name__})"

    async def count(self) -> int:
        try:
            self._apply_global_scopes()
            count_stmt = select(func.count()).select_from(self._stmt.subquery())
            result = await self._session.execute(count_stmt)
            return result.scalar_one()
        finally:
            await self._release_session()

    def _aggregate_subquery(self) -> Any:
        """Build a subquery suitable for aggregate functions.

        Replaces the ORM entity columns with just the table columns so
        SA doesn't generate a cartesian product.
        """
        self._apply_global_scopes()
        return self._stmt.with_only_columns(*self._table.columns).subquery()

    async def max(self, column: _ColumnExpressionOrStrLabelArgument[Any]) -> Any:
        """Return the maximum value for *column*."""
        try:
            sub = self._aggregate_subquery()
            col_name = getattr(column, "key", None) or str(column)
            stmt = select(func.max(sub.c[col_name]))
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            await self._release_session()

    async def min(self, column: _ColumnExpressionOrStrLabelArgument[Any]) -> Any:
        """Return the minimum value for *column*."""
        try:
            sub = self._aggregate_subquery()
            col_name = getattr(column, "key", None) or str(column)
            stmt = select(func.min(sub.c[col_name]))
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            await self._release_session()

    async def sum(self, column: _ColumnExpressionOrStrLabelArgument[Any]) -> Any:
        """Return the sum for *column*."""
        try:
            sub = self._aggregate_subquery()
            col_name = getattr(column, "key", None) or str(column)
            stmt = select(func.sum(sub.c[col_name]))
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            await self._release_session()

    async def avg(self, column: _ColumnExpressionOrStrLabelArgument[Any]) -> Any:
        """Return the average for *column*."""
        try:
            sub = self._aggregate_subquery()
            col_name = getattr(column, "key", None) or str(column)
            stmt = select(func.avg(sub.c[col_name]))
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            await self._release_session()


class RecursiveQueryBuilder[T: DeclarativeBase](QueryBuilder[T]):
    """Query builder for recursive CTE queries.

    Returned by ``QueryBuilder.recursive()``, ``ancestors()``, and
    ``descendants()``.  Terminal methods (``all``, ``first``) produce
    ``TreeNode[T]`` results; ``all_as_tree`` / ``first_as_tree`` build
    a nested hierarchy.
    """

    def __init__(
        self, model_cls: type[T], session: AsyncSession, *, owns_session: bool = False
    ) -> None:
        super().__init__(model_cls, session, owns_session=owns_session)
        self._recursive_id_key: str = "id"
        self._recursive_parent_key: str = "parent_id"

    def _exclude_anchor_row(self, node_id: Any, id_col: Any) -> Self:
        """Filter out the anchor row from results."""
        final_froms = self._stmt.get_final_froms()
        cte_alias = final_froms[0] if final_froms else None
        if cte_alias is not None:
            id_col_name = id_col.name if hasattr(id_col, "name") else "id"
            self._stmt = self._stmt.where(cte_alias.c[id_col_name] != node_id)
        return self

    async def all(self) -> ArvelCollection[TreeNode[T]]:  # ty: ignore[invalid-method-override]
        """Execute the recursive CTE and return flat ``TreeNode`` results."""
        try:
            self._apply_global_scopes()
            result = await self._session.execute(self._stmt)
            col_names = self._get_column_names()
            return ArvelCollection(
                TreeNode.from_row(row._tuple(), col_names) for row in result.all()
            )
        finally:
            await self._release_session()

    async def first(self) -> TreeNode[T] | None:  # ty: ignore[invalid-method-override]
        """Execute the recursive CTE and return the first flat ``TreeNode``."""
        try:
            self._apply_global_scopes()
            result = await self._session.execute(self._stmt)
            col_names = self._get_column_names()
            row = result.first()
            if row is None:
                return None
            return TreeNode.from_row(row._tuple(), col_names)
        finally:
            await self._release_session()

    async def all_as_tree(self) -> ArvelCollection[TreeNode[T]]:
        """Execute the recursive CTE and return a nested tree.

        Flat CTE rows are assembled into a hierarchy using the model's
        self-referencing FK.  Returns only root nodes; children are
        accessible via ``node.children``::

            roots = await Category.query(s).descendants(1).all_as_tree()
            for root in roots:
                for child in root.children:
                    print(child.data["name"], child.depth)
        """
        try:
            result = await self._session.execute(self._stmt)
            col_names = self._get_column_names()
            flat = [TreeNode.from_row(row._tuple(), col_names) for row in result.all()]
            roots = TreeNode.build_tree(
                flat,
                id_key=self._recursive_id_key,
                parent_key=self._recursive_parent_key,
            )
            return ArvelCollection(roots)
        finally:
            await self._release_session()

    async def first_as_tree(self) -> TreeNode[T] | None:
        """Execute the recursive CTE and return the first nested root node.

        The full subtree is nested under the returned node.
        """
        roots = await self.all_as_tree()
        return roots[0] if roots else None

    def __repr__(self) -> str:
        return f"RecursiveQueryBuilder({self._model_cls.__name__})"

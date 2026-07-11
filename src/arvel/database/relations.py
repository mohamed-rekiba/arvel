"""arvel.database.relations — Active-Record relations on the Active-Record Model.

``has_one``/``has_many``/``belongs_to`` with lazy resolution (``await user.posts().get()``)
and **eager loading** (``await User.with_("posts").get()`` → one batched ``WHERE IN``,
no N+1), plus belongs_to_many (pivot), has_many_through, and polymorphic morph_many/
morph_to — all resolved with batched queries, no SQL joins required.
Grounded in knowledge/port/07-orm-active-record.md.
"""
# Relations reach into sibling Model internals within the same package; dynamic by nature.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable


def _morph_type(model: Any) -> str:
    """The stored ``{name}_type`` discriminator for ``model`` (alias or qualified path)."""
    from arvel.database.model import morph_type_of

    return morph_type_of(model)


def _pk_type(model: Any, key: str) -> Any:
    """The SQLAlchemy column type of ``model``'s ``key`` column, so a synthetic pivot column
    matches the real PK type (int / uuid / string) rather than assuming Integer."""
    import sqlalchemy as sa

    try:
        return model.__table__.c[key].type
    except AttributeError, KeyError:
        return sa.Integer()


def _deferred_pivot_query(relation: Any) -> Any:
    """A fresh, **unconstrained** related Builder carrying ``relation``'s pivot-prefetch hook —
    the two-stage ``query()`` shared by the three pivot relation shapes (``BelongsToMany``/
    ``MorphToMany``/``MorphedByMany``). The pivot ``WHERE IN`` is applied in place at terminal
    time by ``relation._apply_pivot_scope`` (DR-0045), so the returned Builder still composes
    with the full proxy surface."""
    from functools import partial

    builder = relation.related.query()
    builder._async_prepare = partial(relation._apply_pivot_scope, builder)
    return builder


class FullBuilderProxy:
    """One ``__getattr__`` proxying any unknown attribute to ``self.query()`` — so a mixing-in
    relation exposes the **full** Builder, scoped to the parent. Mixed into the six shapes with a
    coherent related-query surface (D7); ``query`` itself is provided by the relation shape, never
    by this mixin, so list it **after** the shape in the MRO (``class X(Relation, FullBuilderProxy)``)."""

    query: Callable[[], Any]  # provided by the mixing-in relation shape — annotation only

    def __getattr__(self, name: str) -> Any:
        # never proxy internals/dunders (avoids recursion); real attrs resolve before this fires
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.query(), name)


@dataclass(frozen=True)
class SyncResult:
    """The "changes" map returned by ``BelongsToMany.sync``/``sync_without_detaching``/
    ``sync_with_pivot_values`` — which related ids were attached, detached, and
    had their pivot columns updated (A5)."""

    attached: list[Any] = field(default_factory=list[Any])
    detached: list[Any] = field(default_factory=list[Any])
    updated: list[Any] = field(default_factory=list[Any])


class Relation:
    """Base: a child set keyed by ``foreign_key`` = parent's ``local_key``."""

    def __init__(self, parent: Any, related: Any, foreign_key: str, local_key: str) -> None:
        self.parent = parent
        self.related = related
        self.foreign_key = foreign_key
        self.local_key = local_key

    def _parent_value(self) -> Any:
        return self.parent._attributes.get(self.local_key)

    def query(self) -> Any:
        return self.related.where(self.foreign_key, "=", self._parent_value())

    async def get(self) -> Any:
        return await self.query().get()

    async def first(self) -> Any:
        return await self.query().first()

    def _match(self, items: list[Any]) -> Any:
        from arvel.database.collection import ModelCollection

        return ModelCollection(items)

    def _eager_query(self, keys: list[Any]) -> Any:
        """The batched query loading all children for ``keys`` (subclasses add extra filters)."""
        return self.related.where_in(self.foreign_key, keys)

    async def eager_load(self, parents: list[Any], name: str, constrain: Any = None) -> None:
        keys = [k for p in parents if (k := p._attributes.get(self.local_key)) is not None]
        if not keys:
            for parent in parents:
                parent._relations[name] = self._match([])
            return
        query = self._eager_query(keys)
        if constrain is not None:  # constrained eager load (with_where_has, D2)
            constrain(query)
        children = await query.get()
        grouped: dict[Any, list[Any]] = {}
        for child in children:
            grouped.setdefault(child._attributes.get(self.foreign_key), []).append(child)
        for parent in parents:
            parent._relations[name] = self._match(
                grouped.get(parent._attributes.get(self.local_key), [])
            )

    # --- correlation seams (Builder delegates here) --------------------------
    # Each relation shape knows how its rows correlate to a parent row; Builder's
    # where_has / doesnt_have / with_count-and-friends must not assume a shape.

    def _constrained_where(self, callback: Any) -> Any:
        """The extra WHERE from a user callback, built against the related model's table."""
        from arvel.database.builder import Builder

        constrained = Builder(self.related.__table__, model=self.related)
        callback(constrained)
        return constrained.combined_where()

    def exists_clause(self, parent_table: Any, callback: Any = None) -> Any:
        """EXISTS(1) correlating this relation's rows to ``parent_table`` (has-many shape)."""
        import sqlalchemy as sa

        related_table = self.related.__table__
        subquery = sa.select(sa.literal(1)).where(
            related_table.c[self.foreign_key] == parent_table.c[self.local_key]
        )
        if callback is not None:
            extra = self._constrained_where(callback)
            if extra is not None:
                subquery = subquery.where(extra)
        return sa.exists(subquery)

    def aggregate_clause(self, parent_table: Any, aggregate: Any) -> Any:
        """A correlated scalar subquery of ``aggregate`` over this relation's rows."""
        import sqlalchemy as sa

        related_table = self.related.__table__
        return (
            sa.select(aggregate)
            .where(related_table.c[self.foreign_key] == parent_table.c[self.local_key])
            .scalar_subquery()
        )


class HasOneOrMany(Relation, FullBuilderProxy):
    """has-one / has-many: the child carries the foreign key. A relation **is** a query builder: it proxies ``where``/``order_by``/``count``/… to its FK-constrained query, and
    ``create``/``save`` set the foreign key to the parent automatically."""

    async def create(self, **attributes: Any) -> Any:
        """Create + persist a related child with the foreign key set to the parent."""
        return await self.related.create(**{**attributes, self.foreign_key: self._parent_value()})

    async def save(self, model: Any) -> Any:
        """Persist an existing related model into the relation, setting its foreign key."""
        setattr(model, self.foreign_key, self._parent_value())
        await model.save()
        return model


class HasMany(HasOneOrMany):
    """Parent has many children (children carry the foreign key)."""


class HasOne(HasOneOrMany):
    """Parent has one child."""

    def _match(self, items: list[Any]) -> Any:
        return items[0] if items else None

    async def get(self) -> Any:
        return await self.first()


class BelongsToMany(Relation, FullBuilderProxy):
    """Many-to-many through a pivot table. Resolved with two queries (pivot → WHERE IN)
    so no SQL join is required; supports attach/detach/sync. ``query()`` returns a related
    Builder carrying a deferred async pivot prefetch (DR-0045), so — like ``HasOneOrMany`` —
    the relation proxies the **full** Builder (``where_in``/``pluck``/``order_by``/…), scoped to
    the parent's attached rows."""

    def __init__(
        self,
        parent: Any,
        related: Any,
        pivot: str,
        foreign_pivot_key: str,
        related_pivot_key: str,
        parent_key: str = "id",
        related_key: str = "id",
    ) -> None:
        super().__init__(parent, related, foreign_pivot_key, parent_key)
        self.pivot = pivot
        self.foreign_pivot_key = foreign_pivot_key
        self.related_pivot_key = related_pivot_key
        self.parent_key = parent_key
        self.related_key = related_key
        self._pivot_columns: list[str] = []
        self._pivot_accessor = "pivot"
        self._pivot_wheres: list[tuple[str, Any]] = []

    def with_pivot(self, *columns: str) -> BelongsToMany:
        """Include extra pivot columns, exposed on each result's pivot accessor."""
        self._pivot_columns.extend(columns)
        return self

    def as_(self, accessor: str) -> BelongsToMany:
        """Name the pivot accessor on the related models (default ``pivot``)."""
        self._pivot_accessor = accessor
        return self

    def where_pivot(self, column: str, value: Any) -> BelongsToMany:
        """Constrain the relation by a pivot-table column."""
        self._pivot_wheres.append((column, value))
        return self

    def query(self) -> Any:
        """A fresh, unconstrained related Builder carrying the deferred pivot prefetch — the
        full-builder proxy path (D7). Pivot-specific fluent methods (``where_pivot``/
        ``with_pivot``/``as_``) must be called first: once a Builder method (``where``/
        ``order_by``/…) resolves through here, you're on the Builder, not the relation."""
        return _deferred_pivot_query(self)

    async def _pivot_rows(self) -> Any:
        """This parent's pivot rows, honoring ``where_pivot()`` — the one pre-query shared by the
        proxy's async prefetch hook and the native ``get()``/``count()`` path (DR-0045)."""
        query = self._pivot_query().where(self.foreign_pivot_key, "=", self._parent_id())
        for column, value in self._pivot_wheres:
            query = query.where(column, "=", value)
        return await query.get()

    async def _apply_pivot_scope(self, builder: Any) -> None:
        """The deferred async prefetch: narrow ``builder`` in place to just the attached related
        ids — no attachments forces ``1 = 0`` so an unattached parent yields ``[]``, never the
        whole related table."""
        rows = await self._pivot_rows()
        ids = list({row[self.related_pivot_key] for row in rows})
        if ids:
            builder.where_in(self.related_key, ids)
        else:
            builder.where_raw("1 = 0")

    def _pivot_table(self) -> Any:
        import sqlalchemy as sa

        extra = {*self._pivot_columns, *(col for col, _ in self._pivot_wheres)}
        columns: list[Any] = [
            sa.Column(self.foreign_pivot_key, _pk_type(self.parent, self.parent_key)),
            sa.Column(self.related_pivot_key, _pk_type(self.related, self.related_key)),
            *[cast("Any", sa.Column(col)) for col in extra],
        ]
        return sa.Table(self.pivot, sa.MetaData(), *columns)

    def _pivot_query(self) -> Any:
        from arvel.database.builder import Builder

        return Builder(self._pivot_table(), self.related._resolve())

    def _parent_id(self) -> Any:
        return self.parent._attributes[self.parent_key]

    async def get(self) -> Any:
        """The attached related models, honoring ``where_pivot()`` — enriched with each model's
        pivot accessor when ``with_pivot()`` columns were requested (kept on this native path
        only; the proxied ``.where(...).get()`` doesn't enrich, D7's accepted narrowing)."""
        from arvel.database.collection import ModelCollection

        rows = await self._pivot_rows()
        by_related = {row[self.related_pivot_key]: row for row in rows}
        if not by_related:
            return ModelCollection[Any]()
        models = await self.related.where_in(self.related_key, list(by_related)).get()
        if self._pivot_columns:  # attach the requested pivot data to each model
            for model in models:
                pivot_row = by_related.get(model._attributes[self.related_key])
                if pivot_row is not None:
                    model._attributes[self._pivot_accessor] = {
                        col: pivot_row[col] for col in self._pivot_columns
                    }
        return models

    async def eager_load(self, parents: list[Any], name: str, constrain: Any = None) -> None:
        from arvel.database.collection import ModelCollection

        parent_ids = [k for p in parents if (k := p._attributes.get(self.parent_key)) is not None]
        if not parent_ids:
            for parent in parents:
                parent._relations[name] = ModelCollection[Any]()
            return
        pivot_query = self._pivot_query().where_in(self.foreign_pivot_key, parent_ids)
        for column, value in self._pivot_wheres:
            pivot_query = pivot_query.where(column, "=", value)
        pivot_rows = await pivot_query.get()
        related_ids_by_parent: dict[Any, list[Any]] = {}
        pivot_by_pair: dict[tuple[Any, Any], Any] = {}
        for row in pivot_rows:
            pid, rid = row[self.foreign_pivot_key], row[self.related_pivot_key]
            related_ids_by_parent.setdefault(pid, []).append(rid)
            pivot_by_pair[(pid, rid)] = row

        all_related_ids = list({rid for rids in related_ids_by_parent.values() for rid in rids})
        by_related_id: dict[Any, Any] = {}
        if all_related_ids:
            models_query = self.related.where_in(self.related_key, all_related_ids)
            if constrain is not None:
                constrain(models_query)
            for model in await models_query.get():
                by_related_id[model._attributes[self.related_key]] = model

        for parent in parents:
            pid = parent._attributes.get(self.parent_key)
            matched: list[Any] = []
            for rid in related_ids_by_parent.get(pid, []):
                model = by_related_id.get(rid)
                if model is None:
                    continue
                # without pivot columns, parents share one hydrated instance — read-path
                # aliasing, same tradeoff the reference makes
                if self._pivot_columns:
                    # each parent gets its own hydrated copy so pivot data can't cross parents
                    model = self.related(**dict(model._attributes))
                    pivot_row = pivot_by_pair[(pid, rid)]
                    model._attributes[self._pivot_accessor] = {
                        col: pivot_row[col] for col in self._pivot_columns
                    }
                    model._exists = True
                matched.append(model)
            parent._relations[name] = ModelCollection(matched)

    def _related_where(self, callback: Any = None) -> Any:
        """The related-table WHERE from an extra callback — so where_has/with_count filter exactly
        like a fetch. (D7: the relation no longer accumulates its own where()/order_by() — that's
        the proxy's job now — so this only ever reflects the caller's explicit callback.)"""
        if callback is None:
            return None
        from arvel.database.builder import Builder

        constrained = Builder(self.related.__table__, model=self.related)
        callback(constrained)
        return constrained.combined_where()

    def exists_clause(self, parent_table: Any, callback: Any = None) -> Any:
        import sqlalchemy as sa

        pivot = self._pivot_table()
        related_table = self.related.__table__
        subquery = sa.select(sa.literal(1)).where(
            pivot.c[self.foreign_pivot_key] == parent_table.c[self.parent_key]
        )
        for column, value in self._pivot_wheres:
            subquery = subquery.where(pivot.c[column] == value)
        extra = self._related_where(callback)
        if extra is not None:
            inner = sa.select(sa.literal(1)).where(
                related_table.c[self.related_key] == pivot.c[self.related_pivot_key]
            )
            inner = inner.where(extra)
            subquery = subquery.where(sa.exists(inner))
        return sa.exists(subquery)

    def aggregate_clause(self, parent_table: Any, aggregate: Any) -> Any:
        import sqlalchemy as sa

        pivot = self._pivot_table()
        clause = (
            sa.select(aggregate)
            .select_from(
                pivot.join(
                    self.related.__table__,
                    self.related.__table__.c[self.related_key] == pivot.c[self.related_pivot_key],
                )
            )
            .where(pivot.c[self.foreign_pivot_key] == parent_table.c[self.parent_key])
        )
        for column, value in self._pivot_wheres:
            clause = clause.where(pivot.c[column] == value)
        extra = self._related_where()
        if extra is not None:
            clause = clause.where(extra)
        return clause.scalar_subquery()

    async def attach(self, related_id: Any, **pivot: Any) -> None:
        """Insert a pivot row linking the parent to ``related_id``, with optional extra pivot columns."""
        # the synthetic pivot Table must declare any extra columns being written
        self._pivot_columns.extend(col for col in pivot if col not in self._pivot_columns)
        await self._pivot_query().insert(
            {
                self.foreign_pivot_key: self._parent_id(),
                self.related_pivot_key: related_id,
                **pivot,
            }
        )

    async def detach(self, related_id: Any | None = None) -> None:
        query = self._pivot_query().where(self.foreign_pivot_key, "=", self._parent_id())
        if related_id is not None:
            query = query.where(self.related_pivot_key, "=", related_id)
        await query.delete()

    async def _attached_ids(self) -> set[Any]:
        return set(await self._attached_rows())

    async def _attached_rows(self) -> dict[Any, dict[str, Any]]:
        """Currently-attached pivot rows for the parent, keyed by related id — the full row
        (including any extra pivot columns), used by ``sync`` to diff against."""
        query = self._pivot_query().where(self.foreign_pivot_key, "=", self._parent_id())
        for column, value in self._pivot_wheres:
            query = query.where(column, "=", value)
        return {row[self.related_pivot_key]: dict(row) for row in await query.get()}

    async def sync(
        self, ids_or_mapping: list[Any] | dict[Any, dict[str, Any]], *, detaching: bool = True
    ) -> SyncResult:
        """Diff ``ids_or_mapping`` (a bare id list, or ``{id: pivot_attrs}``) against the currently
        attached ids: attach the missing ones (with any given pivot attrs), update pivot attrs for
        **retained** ids whose given attrs differ from what's stored, and — only when
        ``detaching`` — detach the extras. Retained pivot rows are never dropped/recreated, so
        their data survives untouched unless explicitly given new values (A5: the prior
        detach-then-reattach implementation destroyed it). ``sync``/
        ``syncWithoutDetaching``/``toggle`` parity; returns the changes map."""
        wanted: dict[Any, dict[str, Any]] = (
            dict(ids_or_mapping)
            if isinstance(ids_or_mapping, dict)
            else {related_id: {} for related_id in ids_or_mapping}
        )
        # the synthetic pivot Table must declare every column any wanted row carries, BEFORE
        # reading back the current rows below, or a not-yet-registered column silently reads as
        # absent from `existing` and every retained row looks "changed".
        for attrs in wanted.values():
            self._pivot_columns.extend(col for col in attrs if col not in self._pivot_columns)

        existing = await self._attached_rows()

        attached: list[Any] = []
        updated: list[Any] = []
        for related_id, attrs in wanted.items():
            if related_id not in existing:
                await self.attach(related_id, **attrs)
                attached.append(related_id)
            elif attrs and any(existing[related_id].get(k) != v for k, v in attrs.items()):
                await self.update_existing_pivot(related_id, **attrs)
                updated.append(related_id)

        detached: list[Any] = []
        if detaching:
            for related_id in existing:
                if related_id not in wanted:
                    await self.detach(related_id)
                    detached.append(related_id)

        return SyncResult(attached=attached, detached=detached, updated=updated)

    async def sync_without_detaching(
        self, ids_or_mapping: list[Any] | dict[Any, dict[str, Any]]
    ) -> SyncResult:
        """Attach missing ids (or update given pivot attrs for retained ones), never detaching
        — ``sync(x, detaching=False)``."""
        return await self.sync(ids_or_mapping, detaching=False)

    async def sync_with_pivot_values(
        self, related_ids: list[Any], values: dict[str, Any], *, detaching: bool = True
    ) -> SyncResult:
        """``sync(related_ids)``, attaching/updating every one of them with the same extra pivot
        ``values``."""
        mapping = {related_id: dict(values) for related_id in related_ids}
        return await self.sync(mapping, detaching=detaching)

    async def count(self) -> int:
        """Number of related models currently attached (honors ``where_pivot()``) — a COUNT
        query, not a full load. (Use the proxy — ``rel.where(...).count()`` — to also narrow by
        a related-model column, D7.)"""
        rows = await self._pivot_rows()
        ids = list({row[self.related_pivot_key] for row in rows})
        return 0 if not ids else await self.related.where_in(self.related_key, ids).count()

    async def toggle(self, related_ids: list[Any]) -> dict[str, list[Any]]:
        """Attach the ids that are missing and detach the ones already present (``toggle``); returns the changes map ``{"attached": [...], "detached": [...]}``."""
        existing = await self._attached_ids()
        attached: list[Any] = []
        detached: list[Any] = []
        for related_id in related_ids:
            if related_id in existing:
                await self.detach(related_id)
                detached.append(related_id)
            else:
                await self.attach(related_id)
                attached.append(related_id)
        return {"attached": attached, "detached": detached}

    async def update_existing_pivot(self, related_id: Any, **values: Any) -> None:
        """Update pivot-table columns for an existing attachment."""
        # the synthetic pivot Table must declare the columns being written
        self._pivot_columns.extend(col for col in values if col not in self._pivot_columns)
        await (
            self._pivot_query()
            .where(self.foreign_pivot_key, "=", self._parent_id())
            .where(self.related_pivot_key, "=", related_id)
            .update(values)
        )


class HasManyThrough(Relation):
    """Far relation through an intermediate model (e.g. Country → User → Post)."""

    def __init__(
        self,
        parent: Any,
        related: Any,
        through: Any,
        first_key: str,
        second_key: str,
        local_key: str = "id",
        second_local_key: str = "id",
    ) -> None:
        super().__init__(parent, related, second_key, local_key)
        self.through = through
        self.first_key = first_key
        self.second_key = second_key
        self.local_key = local_key
        self.second_local_key = second_local_key

    async def get(self) -> Any:
        from arvel.database.collection import ModelCollection

        intermediates = await self.through.where(
            self.first_key, "=", self.parent._attributes[self.local_key]
        ).get()
        keys = [row._attributes[self.second_local_key] for row in intermediates]
        if not keys:
            return ModelCollection[Any]()
        return await self.related.where_in(self.second_key, keys).get()

    async def eager_load(self, parents: list[Any], name: str, constrain: Any = None) -> None:
        parent_keys = [k for p in parents if (k := p._attributes.get(self.local_key)) is not None]
        if not parent_keys:
            for parent in parents:
                parent._relations[name] = self._match([])
            return
        intermediates = await self.through.where_in(self.first_key, parent_keys).get()
        # intermediate link value → owning parent key (the far rows join on second_local_key).
        # ponytail: assumes second_local_key is unique (it defaults to the through PK); a
        # non-unique custom key would need multi-parent attribution here.
        parent_key_by_link: dict[Any, Any] = {
            row._attributes[self.second_local_key]: row._attributes[self.first_key]
            for row in intermediates
        }
        grouped: dict[Any, list[Any]] = {}
        if parent_key_by_link:
            query = self.related.where_in(self.second_key, list(parent_key_by_link))
            if constrain is not None:
                constrain(query)
            for child in await query.get():
                owner = parent_key_by_link.get(child._attributes.get(self.second_key))
                grouped.setdefault(owner, []).append(child)
        for parent in parents:
            parent._relations[name] = self._match(
                grouped.get(parent._attributes.get(self.local_key), [])
            )

    def exists_clause(self, parent_table: Any, callback: Any = None) -> Any:
        import sqlalchemy as sa

        through_table = self.through.__table__
        related_table = self.related.__table__
        inner = sa.select(sa.literal(1)).where(
            related_table.c[self.second_key] == through_table.c[self.second_local_key]
        )
        if callback is not None:
            extra = self._constrained_where(callback)
            if extra is not None:
                inner = inner.where(extra)
        subquery = (
            sa.select(sa.literal(1))
            .where(through_table.c[self.first_key] == parent_table.c[self.local_key])
            .where(sa.exists(inner))
        )
        return sa.exists(subquery)

    def aggregate_clause(self, parent_table: Any, aggregate: Any) -> Any:
        import sqlalchemy as sa

        through_table = self.through.__table__
        related_table = self.related.__table__
        return (
            sa.select(aggregate)
            .select_from(
                through_table.join(
                    related_table,
                    related_table.c[self.second_key] == through_table.c[self.second_local_key],
                )
            )
            .where(through_table.c[self.first_key] == parent_table.c[self.local_key])
            .scalar_subquery()
        )


class HasOneThrough(HasManyThrough):
    """Far relation through an intermediate, resolving a single row (or None) — the
    one-row sibling of ``HasManyThrough`` (e.g. Country → User → first Post). D1."""

    def _match(self, items: list[Any]) -> Any:
        return items[0] if items else None

    async def get(self) -> Any:
        rows = await super().get()
        return rows[0] if rows else None


class MorphMany(Relation, FullBuilderProxy):
    """Polymorphic one-to-many: children carry ``{name}_type`` + ``{name}_id``."""

    def __init__(self, parent: Any, related: Any, name: str, local_key: str = "id") -> None:
        super().__init__(parent, related, f"{name}_id", local_key)
        self.morph_name = name

    def query(self) -> Any:
        # overrides Relation.query(): also filter by {name}_type, which the base query() omits —
        # get() is now just the inherited Relation.get() = self.query().get() (D7)
        return self.related.where(
            f"{self.morph_name}_type", "=", _morph_type(type(self.parent))
        ).where(f"{self.morph_name}_id", "=", self.parent._attributes[self.local_key])

    def _eager_query(self, keys: list[Any]) -> Any:
        # also filter by parent type, so children of a different model sharing an id aren't mis-attached
        return self.related.where(
            f"{self.morph_name}_type", "=", _morph_type(type(self.parent))
        ).where_in(self.foreign_key, keys)


class MorphTo(Relation):
    """Polymorphic inverse: resolve the parent named by ``{name}_type``/``{name}_id``."""

    def __init__(self, child: Any, name: str) -> None:
        super().__init__(child, None, f"{name}_id", "id")
        self.morph_name = name

    async def get(self) -> Any:
        from arvel.database.model import resolve_model

        type_name = self.parent._attributes.get(f"{self.morph_name}_type")
        key = self.parent._attributes.get(f"{self.morph_name}_id")
        if type_name is None or key is None:
            return None
        model: Any = resolve_model(type_name)
        return await model.find(key) if model is not None else None

    async def eager_load(self, parents: list[Any], name: str, constrain: Any = None) -> None:
        # the inverse side has no single related model, so the base where_in query doesn't apply:
        # group parents by their {name}_type, then one batched query per distinct type.
        from arvel.database.model import resolve_model

        by_type: dict[str, list[Any]] = {}
        for parent in parents:
            type_name = parent._attributes.get(f"{self.morph_name}_type")
            key = parent._attributes.get(f"{self.morph_name}_id")
            if type_name is not None and key is not None:
                by_type.setdefault(type_name, []).append(parent)

        resolved: dict[tuple[str, Any], Any] = {}
        for type_name, group in by_type.items():
            model: Any = resolve_model(type_name)
            if model is None:
                continue
            pk = model.__primary_key__
            ids = list({p._attributes.get(f"{self.morph_name}_id") for p in group})
            query = model.where_in(pk, ids)
            if constrain is not None:
                constrain(query)
            for row in await query.get():
                resolved[(type_name, row._attributes.get(pk))] = row

        for parent in parents:
            type_name = parent._attributes.get(f"{self.morph_name}_type")
            key = parent._attributes.get(f"{self.morph_name}_id")
            parent._relations[name] = resolved.get((type_name, key))


class MorphOne(MorphMany):
    """Polymorphic one-to-one (the single child for ``{name}_type``/``{name}_id``)."""

    def _match(self, items: list[Any]) -> Any:
        # eager loads hydrate a single model (or None), like HasOne
        return items[0] if items else None

    async def get(self) -> Any:
        results = await super().get()
        return results[0] if results else None


class MorphToMany(Relation, FullBuilderProxy):
    """Polymorphic many-to-many (e.g. a Post ``morph_to_many`` Tags via ``taggables``)."""

    def __init__(self, parent: Any, related: Any, name: str, pivot: str | None = None) -> None:
        super().__init__(parent, related, f"{name}_id", "id")
        from arvel.support import Str

        self.morph_name = name
        self.pivot = pivot or Str.plural(name)
        self.related_pivot_key = f"{Str.snake(related.__name__)}_id"
        self.related_key = related.__primary_key__
        # extra pivot columns (e.g. a team/tenant scope) written by attach() and filterable by
        # where_pivot() — the synthetic pivot Table must declare any column being read or written.
        self._pivot_columns: list[str] = []
        self._pivot_wheres: list[tuple[str, Any]] = []

    def with_pivot(self, *columns: str) -> MorphToMany:
        """Declare extra pivot columns (so ``attach``/``where_pivot`` can read+write them)."""
        self._pivot_columns.extend(c for c in columns if c not in self._pivot_columns)
        return self

    def where_pivot(self, column: str, value: Any) -> MorphToMany:
        """Constrain the relation by an extra pivot column (e.g. ``where_pivot('team_id', 3)``)."""
        if column not in self._pivot_columns:
            self._pivot_columns.append(column)
        self._pivot_wheres.append((column, value))
        return self

    def query(self) -> Any:
        """A fresh, unconstrained related Builder carrying the deferred pivot prefetch (D7)."""
        return _deferred_pivot_query(self)

    async def _pivot_rows(self) -> Any:
        """This parent's pivot rows, honoring ``where_pivot()`` — the one pre-query shared by the
        proxy's async prefetch hook and the native ``get()`` path (DR-0045)."""
        query = (
            self._pivot_query()
            .where(f"{self.morph_name}_id", "=", self._parent_id())
            .where(f"{self.morph_name}_type", "=", _morph_type(type(self.parent)))
        )
        for column, value in self._pivot_wheres:
            query = query.where(column, "=", value)
        return await query.get()

    async def _apply_pivot_scope(self, builder: Any) -> None:
        rows = await self._pivot_rows()
        ids = list({row[self.related_pivot_key] for row in rows})
        if ids:
            builder.where_in(self.related_key, ids)
        else:
            builder.where_raw("1 = 0")

    def _pivot_table(self) -> Any:
        import sqlalchemy as sa

        columns = [
            sa.Column(f"{self.morph_name}_id", _pk_type(self.parent, self.parent.__primary_key__)),
            sa.Column(f"{self.morph_name}_type", sa.String),
            sa.Column(self.related_pivot_key, _pk_type(self.related, self.related.__primary_key__)),
        ]
        columns.extend(sa.Column(c, sa.Integer) for c in self._pivot_columns)
        return sa.Table(self.pivot, sa.MetaData(), *columns)

    def _pivot_query(self) -> Any:
        from arvel.database.builder import Builder

        return Builder(self._pivot_table(), self.related._resolve())

    def _parent_id(self) -> Any:
        return self.parent._attributes[self.parent.__primary_key__]

    async def attach(self, related_id: Any, **pivot: Any) -> None:
        """Link the parent to ``related_id`` (Spatie ``attach``), with optional extra pivot
        columns (e.g. ``attach(role_id, team_id=3)``)."""
        self._pivot_columns.extend(c for c in pivot if c not in self._pivot_columns)
        await self._pivot_query().insert(
            {
                f"{self.morph_name}_id": self._parent_id(),
                f"{self.morph_name}_type": _morph_type(type(self.parent)),
                self.related_pivot_key: related_id,
                **pivot,
            }
        )

    async def detach(self, related_id: Any | None = None, **pivot: Any) -> None:
        """Unlink the parent from ``related_id`` (all related, if ``None``), honoring
        ``where_pivot()`` scope and any extra pivot columns given (e.g. ``detach(role_id,
        team_id=3)``)."""
        self._pivot_columns.extend(c for c in pivot if c not in self._pivot_columns)
        query = (
            self._pivot_query()
            .where(f"{self.morph_name}_id", "=", self._parent_id())
            .where(f"{self.morph_name}_type", "=", _morph_type(type(self.parent)))
        )
        if related_id is not None:
            query = query.where(self.related_pivot_key, "=", related_id)
        for column, value in [*self._pivot_wheres, *pivot.items()]:
            query = query.where(column, "=", value)
        await query.delete()

    async def get(self) -> Any:
        rows = await self._pivot_rows()
        related_ids = list({row[self.related_pivot_key] for row in rows})
        if not related_ids:
            from arvel.database.collection import ModelCollection

            return ModelCollection[Any]()
        return await self.related.where_in(self.related_key, related_ids).get()


class MorphedByMany(Relation, FullBuilderProxy):
    """Inverse polymorphic many-to-many (e.g. a Tag ``morphed_by_many`` Posts)."""

    def __init__(self, parent: Any, related: Any, name: str, pivot: str | None = None) -> None:
        super().__init__(parent, related, f"{name}_id", "id")
        from arvel.support import Str

        self.morph_name = name
        self.pivot = pivot or Str.plural(name)
        self.parent_pivot_key = f"{Str.snake(type(parent).__name__)}_id"
        self.related_key = related.__primary_key__

    def query(self) -> Any:
        """A fresh, unconstrained related Builder carrying the deferred pivot prefetch (D7)."""
        return _deferred_pivot_query(self)

    async def _pivot_rows(self) -> Any:
        """This parent's pivot rows — the one pre-query shared by the proxy's async prefetch
        hook and the native ``get()`` path (DR-0045)."""
        return await (
            self._pivot_query()
            .where(self.parent_pivot_key, "=", self.parent._attributes[self.parent.__primary_key__])
            .where(f"{self.morph_name}_type", "=", _morph_type(self.related))
            .get()
        )

    async def _apply_pivot_scope(self, builder: Any) -> None:
        rows = await self._pivot_rows()
        ids = list({row[f"{self.morph_name}_id"] for row in rows})
        if ids:
            builder.where_in(self.related_key, ids)
        else:
            builder.where_raw("1 = 0")

    def _pivot_query(self) -> Any:
        import sqlalchemy as sa

        from arvel.database.builder import Builder

        table = sa.Table(
            self.pivot,
            sa.MetaData(),
            sa.Column(self.parent_pivot_key, _pk_type(self.parent, self.parent.__primary_key__)),
            sa.Column(
                f"{self.morph_name}_id", _pk_type(self.related, self.related.__primary_key__)
            ),
            sa.Column(f"{self.morph_name}_type", sa.String),
        )
        return Builder(table, self.related._resolve())

    async def get(self) -> Any:
        rows = await self._pivot_rows()
        related_ids = list({row[f"{self.morph_name}_id"] for row in rows})
        if not related_ids:
            from arvel.database.collection import ModelCollection

            return ModelCollection[Any]()
        return await self.related.where_in(self.related_key, related_ids).get()


class BelongsTo(Relation, FullBuilderProxy):
    """Child belongs to an owner (child carries the foreign key → owner's key). Like the other
    relations it **is** a query builder — ``where``/``order_by``/… proxy to the FK-constrained owner
    query — and ``associate``/``dissociate`` set/clear the child's foreign key."""

    def __init__(self, parent: Any, related: Any, foreign_key: str, owner_key: str) -> None:
        super().__init__(parent, related, foreign_key, owner_key)
        self.owner_key = owner_key

    def _parent_value(self) -> Any:
        return self.parent._attributes.get(self.foreign_key)

    def query(self) -> Any:
        return self.related.where(self.owner_key, "=", self._parent_value())

    async def get(self) -> Any:
        return await self.first()

    def associate(self, model: Any) -> Any:
        """Set the child's foreign key to ``model``'s owner key and return the child (``$child->owner()->associate($owner)``). Not persisted until the child is saved."""
        setattr(self.parent, self.foreign_key, model._attributes.get(self.owner_key))
        return self.parent

    def dissociate(self) -> Any:
        """Clear the child's foreign key and return the child."""
        setattr(self.parent, self.foreign_key, None)
        return self.parent

    async def eager_load(self, parents: list[Any], name: str, constrain: Any = None) -> None:
        keys = [k for p in parents if (k := p._attributes.get(self.foreign_key)) is not None]
        if not keys:
            for parent in parents:
                parent._relations[name] = None
            return
        query = self.related.where_in(self.owner_key, keys)
        if constrain is not None:
            constrain(query)
        owners = await query.get()
        by_key = {o._attributes.get(self.owner_key): o for o in owners}
        for parent in parents:
            parent._relations[name] = by_key.get(parent._attributes.get(self.foreign_key))

    def exists_clause(self, parent_table: Any, callback: Any = None) -> Any:
        # inverse shape: the CHILD (query table) carries the foreign key
        import sqlalchemy as sa

        related_table = self.related.__table__
        subquery = sa.select(sa.literal(1)).where(
            related_table.c[self.owner_key] == parent_table.c[self.foreign_key]
        )
        if callback is not None:
            extra = self._constrained_where(callback)
            if extra is not None:
                subquery = subquery.where(extra)
        return sa.exists(subquery)

    def aggregate_clause(self, parent_table: Any, aggregate: Any) -> Any:
        import sqlalchemy as sa

        related_table = self.related.__table__
        return (
            sa.select(aggregate)
            .where(related_table.c[self.owner_key] == parent_table.c[self.foreign_key])
            .scalar_subquery()
        )


class RecursiveRelation:
    """A self-referential **recursive relation** over an adjacency-list tree (a model with a
    ``parent`` foreign key pointing at its own primary key). Built via ``Model.recursive``.

    ``await node.descendants().get()`` → a flat list of hydrated models, each carrying a
    ``depth`` (1 = direct child); ``await node.descendants().tree().get()`` → a nested list of
    dicts (``{…columns, depth, "children": [...]}``). ``direction="up"`` walks ancestors instead.

    Implemented with a ``WITH RECURSIVE`` CTE — so unlike the batched relations it does **not**
    support ``with_()`` eager-loading across many parents at once.
    """

    def __init__(
        self,
        parent: Any,
        related: Any,
        foreign_key: str,
        *,
        local_key: str = "id",
        direction: str = "down",
        depth_key: str = "depth",
    ) -> None:
        self.parent = parent
        self.related = related
        self.foreign_key = foreign_key
        self.local_key = local_key
        self.direction = direction
        self.depth_key = depth_key
        self._as_tree = False
        self._nest_key: str | None = None

    def tree(self, key: str | None = None) -> RecursiveRelation:
        """Switch ``get()`` to return a nested tree (chainable). ``key`` names the nested list
        on each node; it defaults to ``"children"`` for descendants and ``"parents"`` for
        ancestors. Pass any name you like, e.g. ``.tree(key="subitems")``."""
        self._as_tree = True
        self._nest_key = key
        return self

    @property
    def _tree_key(self) -> str:
        if self._nest_key is not None:
            return self._nest_key
        return "parents" if self.direction == "up" else "children"

    def _statement(self) -> Any:
        import sqlalchemy as sa

        t = self.related.__table__
        fk, lk, dk = self.foreign_key, self.local_key, self.depth_key
        if self.direction == "up":  # ancestors: start at this node's parent, walk up
            seed = self.parent._attributes.get(fk)
            anchor = sa.select(t, sa.literal(1).label(dk)).where(t.c[lk] == seed)
            cte = anchor.cte("tree", recursive=True)
            step = sa.select(t, (cte.c[dk] + 1).label(dk)).join(cte, t.c[lk] == cte.c[fk])
        else:  # descendants: start at this node's children, walk down
            seed = self.parent._attributes.get(lk)
            anchor = sa.select(t, sa.literal(1).label(dk)).where(t.c[fk] == seed)
            cte = anchor.cte("tree", recursive=True)
            step = sa.select(t, (cte.c[dk] + 1).label(dk)).join(cte, t.c[fk] == cte.c[lk])
        return sa.select(cte.union_all(step)).order_by(dk)

    async def get(self) -> Any:
        resolver = self.related._resolve()
        rows = [dict(r) for r in await resolver.fetch_all(self._statement())]
        models = [await self.related._hydrate_and_fire(r) for r in rows]
        if self._as_tree:
            return self._nest(models)  # a nested list of dicts, not model instances
        from arvel.database.collection import ModelCollection

        return ModelCollection(models)

    async def eager_load(self, parents: list[Any], name: str, constrain: Any = None) -> None:
        """Batch the whole tree for many parents in **one** ``WITH RECURSIVE`` query (so
        ``with_("descendants")`` is N+1-free): seed every queried node as its own ``__root``,
        walk, drop the seeds, then group each row back to the root it descends from."""
        import sqlalchemy as sa

        t = self.related.__table__
        fk, lk, dk = self.foreign_key, self.local_key, self.depth_key
        ids = [p._attributes.get(lk) for p in parents]
        anchor = sa.select(t, t.c[lk].label("__root"), sa.literal(0).label(dk)).where(
            t.c[lk].in_(ids)
        )
        cte = anchor.cte("tree", recursive=True)
        join_on = (t.c[lk] == cte.c[fk]) if self.direction == "up" else (t.c[fk] == cte.c[lk])
        step = sa.select(t, cte.c["__root"], (cte.c[dk] + 1).label(dk)).join(cte, join_on)
        full = cte.union_all(step)

        from arvel.database.collection import ModelCollection

        resolver = self.related._resolve()
        rows = [dict(r) for r in await resolver.fetch_all(sa.select(full).where(full.c[dk] > 0))]
        grouped: dict[Any, list[Any]] = {}
        for row in rows:
            root = row.pop("__root")  # discriminator, not a model column
            grouped.setdefault(root, []).append(await self.related._hydrate_and_fire(row))
        for parent in parents:
            parent._relations[name] = ModelCollection(grouped.get(parent._attributes.get(lk), []))

    def _nest(self, models: list[Any]) -> list[dict[str, Any]]:
        """Fold the flat, depth-tagged rows into nested ``{…, <key>: [...]}`` dicts. Descendants
        nest each node under its structural parent (key ``children``); ancestors invert it so the
        nearest ancestor is the root and each node nests *its* parent (key ``parents``)."""
        lk, fk, key = self.local_key, self.foreign_key, self._tree_key
        nodes: dict[Any, dict[str, Any]] = {}
        for m in models:
            data = m.to_dict()
            data[key] = []
            nodes[m._attributes[lk]] = data
        roots: list[dict[str, Any]] = []
        if self.direction == "up":
            # root = the nearest ancestor: the one row no other row points to as a parent
            referenced = {m._attributes.get(fk) for m in models}
            for m in models:
                node = nodes[m._attributes[lk]]
                ancestor = nodes.get(m._attributes.get(fk))
                if ancestor is not None:
                    node[key].append(ancestor)
                if m._attributes[lk] not in referenced:
                    roots.append(node)
        else:
            # parent → children: nest each node under its structural parent.
            for m in models:
                node = nodes[m._attributes[lk]]
                parent_node = nodes.get(m._attributes.get(fk))
                (parent_node[key] if parent_node is not None else roots).append(node)
        return roots

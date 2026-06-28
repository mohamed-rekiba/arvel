"""arvel.database.relations — Eloquent-style relations on the Active-Record Model.

``has_one``/``has_many``/``belongs_to`` with lazy resolution (``await user.posts().get()``)
and **eager loading** (``await User.with_("posts").get()`` → one batched ``WHERE IN``,
no N+1), plus belongs_to_many (pivot), has_many_through, and polymorphic morph_many/
morph_to — all resolved with batched queries, no SQL joins required.
Grounded in knowledge/port/07-orm-active-record.md.
"""
# Relations reach into sibling Model internals within the same package; dynamic by nature.

from __future__ import annotations

from typing import Any, cast


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
        return items

    def _eager_query(self, keys: list[Any]) -> Any:
        """The batched query loading all children for ``keys`` (subclasses add extra filters)."""
        return self.related.where_in(self.foreign_key, keys)

    async def eager_load(self, parents: list[Any], name: str, constrain: Any = None) -> None:
        keys = [p._attributes.get(self.local_key) for p in parents]
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


class HasOneOrMany(Relation):
    """has-one / has-many: the child carries the foreign key. A relation **is** a query builder
    (Laravel): it proxies ``where``/``order_by``/``count``/… to its FK-constrained query, and
    ``create``/``save`` set the foreign key to the parent automatically."""

    def __getattr__(self, name: str) -> Any:
        # Only proxy genuine query-builder calls — never internals/dunders (avoids recursion and
        # keeps `hasattr` honest). `query`, `get`, `first`, `create`, `save` are real attributes,
        # so they're resolved before this ever fires.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.query(), name)

    async def create(self, **attributes: Any) -> Any:
        """Create + persist a related child with the foreign key set to the parent
        (Laravel ``$parent->children()->create([...])``)."""
        return await self.related.create(**{**attributes, self.foreign_key: self._parent_value()})

    async def save(self, model: Any) -> Any:
        """Persist an existing related model into the relation, setting its foreign key
        (Laravel ``$parent->children()->save($child)``)."""
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


class BelongsToMany(Relation):
    """Many-to-many through a pivot table. Resolved with two queries (pivot → WHERE IN)
    so no SQL join is required; supports attach/detach/sync."""

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
        self._related_constraints: list[Any] = []  # where/order_by on the related model query

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

    def where(self, *args: Any) -> BelongsToMany:
        """Constrain the **related** model query (Laravel ``$user->roles()->where('active', true)``).
        Applied to the second-stage related-model fetch, within the pivot-filtered set."""

        def constrain(query: Any) -> None:
            query.where(*args)

        self._related_constraints.append(constrain)
        return self

    def order_by(self, column: str, direction: str = "asc") -> BelongsToMany:
        """Order the related models (applied to the related-model fetch)."""

        def constrain(query: Any) -> None:
            query.order_by(column, direction)

        self._related_constraints.append(constrain)
        return self

    def _pivot_table(self) -> Any:
        import sqlalchemy as sa

        extra = {*self._pivot_columns, *(col for col, _ in self._pivot_wheres)}
        columns: list[Any] = [
            sa.Column(self.foreign_pivot_key, sa.Integer),
            sa.Column(self.related_pivot_key, sa.Integer),
            *[cast("Any", sa.Column(col)) for col in extra],
        ]
        return sa.Table(self.pivot, sa.MetaData(), *columns)

    def _pivot_query(self) -> Any:
        from arvel.database.builder import Builder

        return Builder(self._pivot_table(), self.related._resolve())

    def _parent_id(self) -> Any:
        return self.parent._attributes[self.parent_key]

    async def get(self) -> Any:
        query = self._pivot_query().where(self.foreign_pivot_key, "=", self._parent_id())
        for column, value in self._pivot_wheres:
            query = query.where(column, "=", value)
        rows = await query.get()
        by_related = {row[self.related_pivot_key]: row for row in rows}
        if not by_related:
            return []
        models_query = self.related.where_in(self.related_key, list(by_related))
        for constrain in self._related_constraints:  # where()/order_by() on the related model
            constrain(models_query)
        models = await models_query.get()
        if self._pivot_columns:  # attach the requested pivot data to each model
            for model in models:
                pivot_row = by_related.get(model._attributes[self.related_key])
                if pivot_row is not None:
                    model._attributes[self._pivot_accessor] = {
                        col: pivot_row[col] for col in self._pivot_columns
                    }
        return models

    async def attach(self, related_id: Any, **pivot: Any) -> None:
        """Insert a pivot row linking the parent to ``related_id``, with optional extra pivot columns
        (Laravel ``attach($id, ['col' => 'val'])``)."""
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

    async def sync(self, related_ids: list[Any]) -> None:
        await self.detach()
        for related_id in related_ids:
            await self.attach(related_id)

    async def count(self) -> int:
        """Number of related models currently attached (honors where()/where_pivot())."""
        return len(await self.get())

    async def _attached_ids(self) -> set[Any]:
        query = self._pivot_query().where(self.foreign_pivot_key, "=", self._parent_id())
        for column, value in self._pivot_wheres:
            query = query.where(column, "=", value)
        return {row[self.related_pivot_key] for row in await query.get()}

    async def sync_without_detaching(self, related_ids: list[Any]) -> None:
        """Attach any ``related_ids`` not already attached, leaving existing links intact
        (Laravel ``syncWithoutDetaching``)."""
        existing = await self._attached_ids()
        for related_id in related_ids:
            if related_id not in existing:
                await self.attach(related_id)

    async def toggle(self, related_ids: list[Any]) -> None:
        """Attach the ids that are missing and detach the ones already present (Laravel ``toggle``)."""
        existing = await self._attached_ids()
        for related_id in related_ids:
            if related_id in existing:
                await self.detach(related_id)
            else:
                await self.attach(related_id)

    async def update_existing_pivot(self, related_id: Any, **values: Any) -> None:
        """Update pivot-table columns for an existing attachment (Laravel ``updateExistingPivot``)."""
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
        intermediates = await self.through.where(
            self.first_key, "=", self.parent._attributes[self.local_key]
        ).get()
        keys = [row._attributes[self.second_local_key] for row in intermediates]
        if not keys:
            return []
        return await self.related.where_in(self.second_key, keys).get()


class HasOneThrough(HasManyThrough):
    """Far relation through an intermediate, resolving a single row (or None) — the
    one-row sibling of ``HasManyThrough`` (e.g. Country → User → first Post). D1."""

    async def get(self) -> Any:
        rows = await super().get()
        return rows[0] if rows else None


class MorphMany(Relation):
    """Polymorphic one-to-many: children carry ``{name}_type`` + ``{name}_id``."""

    def __init__(self, parent: Any, related: Any, name: str, local_key: str = "id") -> None:
        super().__init__(parent, related, f"{name}_id", local_key)
        self.morph_name = name

    async def get(self) -> Any:
        return await (
            self.related.where(f"{self.morph_name}_type", "=", type(self.parent).__name__)
            .where(f"{self.morph_name}_id", "=", self.parent._attributes[self.local_key])
            .get()
        )

    def _eager_query(self, keys: list[Any]) -> Any:
        # Polymorphic: also filter by the parent type, so children of a different model that
        # happen to share an id are never mis-attached during eager loading.
        return self.related.where(
            f"{self.morph_name}_type", "=", type(self.parent).__name__
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


class MorphOne(MorphMany):
    """Polymorphic one-to-one (the single child for ``{name}_type``/``{name}_id``)."""

    async def get(self) -> Any:
        results = await super().get()
        return results[0] if results else None


class MorphToMany(Relation):
    """Polymorphic many-to-many (e.g. a Post ``morph_to_many`` Tags via ``taggables``)."""

    def __init__(self, parent: Any, related: Any, name: str, pivot: str | None = None) -> None:
        super().__init__(parent, related, f"{name}_id", "id")
        from arvel.support import Str

        self.morph_name = name
        self.pivot = pivot or Str.plural(name)
        self.related_pivot_key = f"{Str.snake(related.__name__)}_id"

    def _pivot_table(self) -> Any:
        import sqlalchemy as sa

        return sa.Table(
            self.pivot,
            sa.MetaData(),
            sa.Column(f"{self.morph_name}_id", sa.Integer),
            sa.Column(f"{self.morph_name}_type", sa.String),
            sa.Column(self.related_pivot_key, sa.Integer),
        )

    def _pivot_query(self) -> Any:
        from arvel.database.builder import Builder

        return Builder(self._pivot_table(), self.related._resolve())

    def _parent_id(self) -> Any:
        return self.parent._attributes["id"]

    async def attach(self, related_id: Any) -> None:
        await self._pivot_query().insert(
            {
                f"{self.morph_name}_id": self._parent_id(),
                f"{self.morph_name}_type": type(self.parent).__name__,
                self.related_pivot_key: related_id,
            }
        )

    async def get(self) -> Any:
        rows = await (
            self._pivot_query()
            .where(f"{self.morph_name}_id", "=", self._parent_id())
            .where(f"{self.morph_name}_type", "=", type(self.parent).__name__)
            .get()
        )
        related_ids = [row[self.related_pivot_key] for row in rows]
        if not related_ids:
            return []
        return await self.related.where_in("id", related_ids).get()


class MorphedByMany(Relation):
    """Inverse polymorphic many-to-many (e.g. a Tag ``morphed_by_many`` Posts)."""

    def __init__(self, parent: Any, related: Any, name: str, pivot: str | None = None) -> None:
        super().__init__(parent, related, f"{name}_id", "id")
        from arvel.support import Str

        self.morph_name = name
        self.pivot = pivot or Str.plural(name)
        self.parent_pivot_key = f"{Str.snake(type(parent).__name__)}_id"

    def _pivot_query(self) -> Any:
        import sqlalchemy as sa

        from arvel.database.builder import Builder

        table = sa.Table(
            self.pivot,
            sa.MetaData(),
            sa.Column(self.parent_pivot_key, sa.Integer),
            sa.Column(f"{self.morph_name}_id", sa.Integer),
            sa.Column(f"{self.morph_name}_type", sa.String),
        )
        return Builder(table, self.related._resolve())

    async def get(self) -> Any:
        rows = await (
            self._pivot_query()
            .where(self.parent_pivot_key, "=", self.parent._attributes["id"])
            .where(f"{self.morph_name}_type", "=", self.related.__name__)
            .get()
        )
        related_ids = [row[f"{self.morph_name}_id"] for row in rows]
        if not related_ids:
            return []
        return await self.related.where_in("id", related_ids).get()


class BelongsTo(Relation):
    """Child belongs to an owner (child carries the foreign key → owner's key). Like the other
    relations it **is** a query builder — ``where``/``order_by``/… proxy to the FK-constrained owner
    query — and ``associate``/``dissociate`` set/clear the child's foreign key (Laravel)."""

    def __init__(self, parent: Any, related: Any, foreign_key: str, owner_key: str) -> None:
        super().__init__(parent, related, foreign_key, owner_key)
        self.owner_key = owner_key

    def __getattr__(self, name: str) -> Any:
        # Proxy query-builder calls to the owner query; never internals/dunders (avoids recursion,
        # keeps hasattr honest). Real attrs/methods (owner_key/query/get/associate/...) resolve first.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.query(), name)

    def _parent_value(self) -> Any:
        return self.parent._attributes.get(self.foreign_key)

    def query(self) -> Any:
        return self.related.where(self.owner_key, "=", self._parent_value())

    async def get(self) -> Any:
        return await self.first()

    def associate(self, model: Any) -> Any:
        """Set the child's foreign key to ``model``'s owner key and return the child (Laravel
        ``$child->owner()->associate($owner)``). Not persisted until the child is saved."""
        setattr(self.parent, self.foreign_key, model._attributes.get(self.owner_key))
        return self.parent

    def dissociate(self) -> Any:
        """Clear the child's foreign key and return the child (Laravel ``dissociate``)."""
        setattr(self.parent, self.foreign_key, None)
        return self.parent

    async def eager_load(self, parents: list[Any], name: str, constrain: Any = None) -> None:
        keys = [p._attributes.get(self.foreign_key) for p in parents]
        query = self.related.where_in(self.owner_key, keys)
        if constrain is not None:
            constrain(query)
        owners = await query.get()
        by_key = {o._attributes.get(self.owner_key): o for o in owners}
        for parent in parents:
            parent._relations[name] = by_key.get(parent._attributes.get(self.foreign_key))


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
        models = [self.related._hydrate(r) for r in rows]
        return self._nest(models) if self._as_tree else models

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

        resolver = self.related._resolve()
        rows = [dict(r) for r in await resolver.fetch_all(sa.select(full).where(full.c[dk] > 0))]
        grouped: dict[Any, list[Any]] = {}
        for row in rows:
            root = row.pop("__root")  # discriminator, not a model column
            grouped.setdefault(root, []).append(self.related._hydrate(row))
        for parent in parents:
            parent._relations[name] = grouped.get(parent._attributes.get(lk), [])

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
            # child → parent: each node nests the row that is its parent in the chain; the root
            # is the nearest ancestor (no other row points to it as a parent).
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

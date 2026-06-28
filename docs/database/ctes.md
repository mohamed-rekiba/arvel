# CTEs & Recursive Queries

The tools below are **general-purpose SQL features**, not relation helpers — CTEs and recursive
queries work on any query (a number series, a running total, a graph walk), and only the last
piece, the referential-tree relation, is about a model pointing back at itself. Reach for them
when a plain query or relation can't express the shape.

## CTEs (`WITH`)

A Common Table Expression names a subquery so you can reference it like a table — it makes a
complex query readable and lets you reuse an intermediate result instead of repeating it. It is
a **general query tool**, not tied to relations. Turn any arvel query into one with
`to_cte(name)`, then compose with SQLAlchemy Core:

```python
import sqlalchemy as sa
from arvel.kernel import app

db = app("db")

# name an expensive per-user aggregate once, then join against it
spend = (
    sa.select(orders.c.user_id, sa.func.sum(orders.c.total).label("spent"))
    .group_by(orders.c.user_id)
    .cte("spend")
)
stmt = sa.select(users, spend.c.spent).join(spend, users.c.id == spend.c.user_id)
big_spenders = await db.fetch_all(stmt.where(spend.c.spent > 1000))

recent = Post.where("created_at", ">", cutoff).to_cte("recent")   # …or start from a model
```

## Recursive queries (`WITH RECURSIVE`)

A **recursive CTE** repeats a query, feeding each pass's rows back in — for **any** iterative
shape, not just trees: a number or date series, a running total, graph traversal, a
bill-of-materials explosion. It's always *anchor* (seed rows) `UNION ALL` *recursive term*
(which references the CTE). Here's one with no source table at all — generate `1..10`:

```python
import sqlalchemy as sa
from arvel.kernel import app

nums = sa.select(sa.literal(1).label("n")).cte("nums", recursive=True)
nums = nums.union_all(sa.select((nums.c.n + 1).label("n")).where(nums.c.n < 10))
rows = await app("db").fetch_all(sa.select(nums))     # [{"n": 1}, … {"n": 10}]
```

For the common **referential tree** case there's an ergonomic relation (below); for any
other recursion, build the CTE by hand and — if you want models back — re-source a builder onto
it with `Builder.from_cte()`.

## Referential trees

A model whose `parent_id` points back at its own key is a **referential** (self-referencing,
adjacency-list) tree — categories under categories, comments under comments, employees under a
manager. Direct links are ordinary relations; whole branches come from `recursive()`, declared
just like any other relation:

```python
class Category(Model):
    __fillable__ = ["name", "parent_id"]

    def children(self):    return self.has_many(Category, foreign_key="parent_id")      # one level
    def parent(self):      return self.belongs_to(Category, foreign_key="parent_id")
    def descendants(self): return self.recursive(Category, "parent_id")                 # walk down
    def ancestors(self):   return self.recursive(Category, "parent_id", direction="up") # walk up
```

`.get()` returns a **flat** list of models, each carrying a `depth` (1 = direct child/parent);
`.tree().get()` returns a **nested** structure:

```python
await category.children().get()            # immediate children (a plain relation)

flat = await category.descendants().get()  # every descendant, each with .depth
for n in flat:
    print("  " * n.depth, n.name)          # indent by depth → a printable tree

await category.ancestors().get()           # the parent chain upward, each with .depth

await category.descendants().tree().get()
# nests under "children" (the default for descendants):
# [{"name": "phones", "depth": 1, "children": [
#       {"name": "smartphones", "depth": 2, "children": []}]},
#  {"name": "laptops", "depth": 1, "children": []}]

await category.ancestors().tree().get()
# ancestors invert: the nearest ancestor is the root, and the key defaults to "parents":
# [{"name": "phones", "depth": 1, "parents": [
#       {"name": "electronics", "depth": 2, "parents": []}]}]

await category.descendants().tree(key="subitems").get()   # …or name the nested key yourself
```

Eager-load them like any relation — a recursive relation batches **all** the subtrees into a
single `WITH RECURSIVE` query (no N+1):

```python
roots = await Category.where(parent_id=None).with_("descendants").get()
roots[0].relation("descendants")          # the first root's whole subtree, already loaded
```

> **Gotcha — cycles.** A recursive query over a graph with a cycle (A→B→A) won't terminate.
> Guard your data or cap the depth before recursing on user input.

For **custom** recursion beyond a parent/child tree, build the recursive CTE yourself and
re-source a builder onto it with `from_cte()` — `.get()` still hydrates the rows into models:

```python
import sqlalchemy as sa
from arvel.database import Builder

t    = Category.__table__
base = Builder(t).where(id=root_id).to_select().cte("tree", recursive=True)
full = base.union_all(sa.select(t).join(base, t.c.parent_id == base.c.id))
rows = await Builder(t, db, hydrate=Category._hydrate, model=Category).from_cte(full).get()
```

# Arvent ORM

**Arvent** is Arvel's active-record ORM on SQLAlchemy's async engine. Models are typed Python classes; queries are fluent; migrations use a Laravel-style DSL.

## Recommended path

1. **[Models & CRUD](models.md)** — define a model, create/read/update/delete, mixins, factories.
2. **[Migrations](migrations.md)** — schema DSL, rollbacks, seeders, `migrate:fresh` guards.
3. **[Relationships](relationships.md)** — has-many, belongs-to, many-to-many, polymorphic, eager loading.
4. **[Query Builder](query-builder.md)** — `where`, joins, subqueries, pagination, transactions.
5. **[Casts, Accessors & Mutators](casts.md)** — JSON columns, encryption, computed attributes, translations.

```python
flight = await Flight.create(name="London to Paris")
rows = await Flight.where(is_active=True).with_("airline").paginate(page=1)
await flight.delete()
```

## What's in this section

| Page | Covers |
|---|---|
| [Models & CRUD](models.md) | Columns, `Timestamps`, scopes, observers, pruning |
| [Relationships](relationships.md) | Eager load, constraints, has-one-of-many, chaperone |
| [Query Builder](query-builder.md) | Aggregates, subqueries, `DB` facade, query log |
| [Migrations](migrations.md) | Blueprint DSL, pivots, factories, seeders |
| [Casts, Accessors & Mutators](casts.md) | `AsArray`, encrypted columns, `TranslatableMixin` |

## See also

- [Database CLI](../cli/commands.md#migrate) — `migrate`, `db:seed`, `model:show`.
- [Testing](../features/testing.md#database-testing) — `RefreshDatabase` for isolated tests.

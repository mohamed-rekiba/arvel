# Type Safety Analysis

Arvel enforces end-to-end type safety across its public API surface. This document explains the patterns used, the rationale behind each, and the tools that verify them.

---

## Philosophy

Type safety in Arvel follows one rule: **the boundary is what matters**. Every public API (exported functions, methods, class attributes) must give type checkers correct inference. Internal code can use pragmatic `Any` where the cost of precision exceeds the benefit — but that `Any` must never leak to consumers.

---

## Key Patterns

### 1. `Mapped[T]` for All Model Columns

SQLAlchemy 2.0's `Mapped[T]` annotation gives type checkers column types at the class level:

```python
id: Mapped[int] = mapped_column(primary_key=True)
name: Mapped[str] = mapped_column(String(255))
bio: Mapped[str | None]  # nullable
```

Legacy `Column()` is reserved for Core-layer usage only (pivot tables, raw SQL).

### 2. `Generic[T]` on Model-Scoped Classes

`Repository[T]`, `QueryBuilder[T]`, `ModelObserver[T]`, and `ModelFactory[T]` all preserve the model type through generics:

```python
class UserRepository(Repository[User]):
    async def find_by_email(self, email: str) -> User | None:
        return await self.query().where(User.email == email).first()
```

The type checker knows that `find_by_email` returns `User | None`, not `Any`.

### 3. `Self` for Fluent APIs

Methods that return the same type use `Self` to preserve the concrete class:

```python
def where(self, *criteria: ColumnElement[bool]) -> Self:
    self._stmt = self._stmt.where(*criteria)
    return self
```

This means `User.query(session).where(...)` returns `QueryBuilder[User]`, not `QueryBuilder[DeclarativeBase]`.

### 4. Contract Interfaces

Every infrastructure concern defines a typed contract:

```python
class CacheContract(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def put(self, key: str, value: Any, ttl: int) -> None: ...
```

Drivers implement the contract. Fakes implement the contract. The DI container binds `CacheContract → RedisDriver` (or `MemoryDriver`, or `CacheFake`). Consumer code depends only on the contract type.

### 5. Constructor Injection via Type Hints

The DI container resolves parameters by introspecting `__init__` type hints:

```python
class OrderService:
    def __init__(self, repo: OrderRepository, mailer: MailContract) -> None:
        ...
```

`Annotated[T, ...]` is unwrapped to `T` before resolution, so `Annotated[UserService, Depends(...)]` resolves `UserService`.

### 6. `@overload` for Input-Dependent Return Types

When a function's return type depends on the input type, `@overload` provides precise inference:

```python
@overload
def has_one(related: type[T], **kw: Any) -> T: ...
@overload
def has_one(related: str, **kw: Any) -> Any: ...
```

### 7. Typed Settings via Pydantic

Every configuration module uses `pydantic-settings.BaseSettings` subclasses with explicit types:

```python
class CacheSettings(ModuleSettings):
    driver: str = "memory"
    prefix: str = ""
    default_ttl: int = 3600
    redis_url: str = "redis://localhost:6379/0"
```

No `dict[str, Any]` for structured configuration.

---

## Verification

### ty (Type Checker)

```bash
ty check src/arvel/
```

Configured in `pyproject.toml`:

```toml
[tool.ty.environment]
python-version = "3.14"
```

### Ruff (Annotation Linting)

```toml
[tool.ruff.lint]
select = [
    "TCH",   # TYPE_CHECKING imports
    "ANN",   # Missing type annotations
    "UP",    # pyupgrade — modern syntax
]
```

### Pre-Commit

Both `ty` and `ruff` run as pre-commit hooks, catching type issues before they reach CI.

---

## Forbidden Patterns

| Pattern | Why | Fix |
|---------|-----|-----|
| `Any` in public signatures | Erases type info for consumers | Use concrete types, generics, or `@overload` |
| `dict[str, Any]` for structured data | Loses field-level types | Use `TypedDict`, `BaseModel`, or dataclass |
| `setattr` for typed attributes | Invisible to type checkers | Declare attributes on the class |
| `cast` without invariant guarantee | Unsound — runtime type may differ | Use `TypeGuard` or restructure |
| Silent `return self` on error | Hides failures from callers | Raise with context |

---

## Checklist

Before merging any change:

- [ ] No new `Any` in public function signatures
- [ ] No new `dict[str, Any]` for structured data in public APIs
- [ ] No new `setattr` for typed attributes
- [ ] `@overload` used when return type depends on input
- [ ] `Self` used on fluent/factory methods
- [ ] `TypeGuard` used instead of `isinstance` + manual narrowing
- [ ] All re-exports use `X as X` pattern
- [ ] `ty check src/arvel/` passes with zero new errors

# Testing Best Practices

Every test must be deterministic, isolated, and fast.

---

## Golden Rules

1. **No test ordering dependencies** — every test passes in isolation and in any order
2. **No shared mutable state** — use fixtures, not module-level variables
3. **No lazy loading in async tests** — always eager-load relationships
4. **No mocking framework internals** — test `Repository` and `QueryBuilder` against a real (SQLite) database
5. **No hardcoded service URLs** — use env vars or fixtures

---

## Test Naming

```python
# Pattern: test_<what>_<condition>_<expected>
def test_create_user_with_valid_data_returns_user(): ...
def test_create_user_with_duplicate_email_raises_integrity_error(): ...
def test_find_nonexistent_user_returns_none(): ...
```

---

## Transaction Rollback Isolation

Every DB test runs inside a transaction that rolls back:

```python
@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{_TEST_DB_PATH}")
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
            if trans.is_active:
                await trans.rollback()
    await engine.dispose()
```

Always enable FK enforcement in SQLite:

```python
@event.listens_for(engine.sync_engine, "connect")
def _enable_fk(dbapi_conn, _record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

---

## Assertion Patterns

### Triple Assertion (Status + Body + Headers)

```python
def test_unauthorized():
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
```

### Structured Assertions with `dirty-equals`

```python
from dirty_equals import IsUUID, IsDatetime

assert response.json() == {
    "id": IsUUID(4),
    "name": "Alice",
    "created_at": IsDatetime,
}
```

### Exception Assertions with Context

```python
async def test_find_nonexistent_raises():
    with pytest.raises(NotFoundError, match="User"):
        await repo.find(999)
```

---

## Parametrize with Named IDs

```python
@pytest.mark.parametrize(
    ("input_data", "expected"),
    [
        pytest.param({"name": ""}, "empty", id="empty-name"),
        pytest.param({"name": "x" * 256}, "too-long", id="name-too-long"),
    ],
)
```

---

## Markers

```python
@pytest.mark.db
async def test_create_user(db_session): ...

@pytest.mark.integration
@pytest.mark.redis
async def test_cache_set(redis_client): ...
```

---

## Factory Usage

```python
user = UserFactory.make(name="Alice", email="alice@test.com")
user = await UserFactory.create(session=db_session, name="Bob")
admin = await UserFactory.state("admin").create(session=db_session)
```

---

## Fakes for Unit Tests, Real Drivers for Integration

```python
# Unit test — use fake
async def test_send_notification():
    notifier = NotificationFake()
    await notifier.send(user, WelcomeNotification())
    notifier.assert_sent_count(1)

# Integration test — use real driver
@pytest.mark.integration
@pytest.mark.smtp
async def test_send_real_email(smtp_config):
    mailer = SmtpMailDriver(smtp_config)
    await mailer.send(to="test@example.com", subject="Test")
```

---

## Async Testing

1. Root `conftest.py` auto-marks `async def` tests with `@pytest.mark.anyio`
2. Data tests pinned to asyncio (`anyio_backend = "asyncio"` because aiosqlite is asyncio-only)
3. Don't mix sync and async clients

---

## Fixture Scoping

| Scope | Use For | Dispose |
|-------|---------|---------|
| `session` | Table creation | After all tests |
| `module` | `anyio_backend` | After file completes |
| `function` | DB session, client | After each test |

---

## Contract Testing

Every infrastructure ABC has a shared test class all drivers pass:

```python
class CacheContractTest:
    @pytest.fixture
    def cache(self) -> CacheDriver:
        raise NotImplementedError

    async def test_set_and_get(self, cache): ...
    async def test_get_missing_returns_none(self, cache): ...
    async def test_delete(self, cache): ...

class TestMemoryCache(CacheContractTest):
    @pytest.fixture
    def cache(self):
        return MemoryCacheDriver()
```

---

## Coverage

```bash
# Local
pytest --cov=src/arvel --cov-report=term-missing --cov-fail-under=80

# CI
pytest --cov --cov-context=test --cov-report=xml
coverage combine && coverage report --fail-under=80
```

Branch coverage enabled via `[tool.coverage.run] branch = true`.

---

## CI Test Splitting

```bash
# Fast (no services, < 30 seconds)
pytest -m "not db and not integration" --timeout=10

# DB only (SQLite, no external services)
pytest -m "db and not pg_only and not integration"

# Full integration (all services, CI only)
pytest -v --cov
```

---

## Forbidden Patterns

| Pattern | Fix |
|---------|-----|
| Shared mutable state | Per-test fixtures |
| Mocking framework internals | Real repo against real DB |
| Broad `pytest.raises(Exception)` | Specific exception type |
| Ignoring response body | Assert status + body + headers |
| Raw `os.environ` mutation | `monkeypatch.setenv()` |
| Unbounded async without timeout | `anyio.fail_after(5)` |

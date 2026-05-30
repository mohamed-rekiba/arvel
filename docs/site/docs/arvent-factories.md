# Factories

Factories generate model instances with realistic test data. Use them in tests and seeders to avoid hand-coding the same example users, posts, and orders over and over.

## Defining a factory

```python
from arvel.database import Factory

from app.models import User


class UserFactory(Factory[User]):
    model = User

    def definition(self) -> dict:
        return {
            "name": self.faker.name(),
            "email": self.faker.unique.email(),
            "password_hash": "$2b$12$dummy-hash-for-tests",
        }
```

`self.faker` is a [Faker](https://faker.readthedocs.io/) instance preconfigured with the application locale. Use `self.faker.unique.X` for values that need to be unique across the entire test run (Faker tracks generated values and reseeds when exhausted).

## Creating instances

```python
user = await UserFactory().create()                       # single, saved
users = await UserFactory().count(20).create()             # 20, saved
user_data = UserFactory().make()                           # built but not saved
```

`create()` writes to the database; `make()` returns the in-memory instance.

## Overriding attributes

```python
admin = await UserFactory().create(role="admin")
alice = await UserFactory().create(email="alice@example.com")
```

Any kwargs passed to `create()` override the factory's defaults for that one call.

## States

For named variants:

```python
class UserFactory(Factory[User]):
    model = User

    def definition(self) -> dict:
        return {"name": self.faker.name(), "email": self.faker.unique.email()}

    def admin(self) -> "UserFactory":
        return self.state({"role": "admin", "is_admin": True})

    def banned(self) -> "UserFactory":
        return self.state({"banned_at": self.faker.past_datetime()})


admin = await UserFactory().admin().create()
banned_user = await UserFactory().banned().create()
```

States are chainable; later states override earlier ones.

## Relationships

Use a related factory inside `definition()`:

```python
class PostFactory(Factory[Post]):
    model = Post

    def definition(self) -> dict:
        return {
            "title": self.faker.sentence(),
            "body": self.faker.text(),
            "author_id": lambda: UserFactory().create_one_async(),
        }
```

The callable is evaluated lazily, once per generated row.

For higher-level relationship sugar:

```python
class PostFactory(Factory[Post]):
    def for_user(self, user) -> "PostFactory":
        return self.state({"author_id": user.id})

    def with_comments(self, count: int = 3) -> "PostFactory":
        async def attach(post):
            await CommentFactory().for_post(post).count(count).create()
        return self.after_create(attach)


posts = await PostFactory().with_comments(5).count(10).create()
```

`after_create` callbacks run after each model is saved.

## Sequences

For values that must increment across instances:

```python
class UserFactory(Factory[User]):
    def definition(self) -> dict:
        return {
            "email": self.sequence(lambda n: f"user{n}@example.com"),
        }


users = await UserFactory().count(3).create()
# emails: user0@example.com, user1@example.com, user2@example.com
```

## Recycling existing models

When a relationship should reuse existing records instead of creating new ones:

```python
class CommentFactory(Factory[Comment]):
    def for_user(self, user) -> "CommentFactory":
        return self.state({"author_id": user.id})


alice = await UserFactory().create()
comments = await CommentFactory().for_user(alice).count(20).create()
# All 20 comments share the same author
```

## In seeders

```python
class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        admin = await UserFactory().admin().create(email="admin@example.com")
        users = await UserFactory().count(20).create()

        for user in users:
            await PostFactory().for_user(user).with_comments(3).count(5).create()
```

## Where to next?

- [Seeding](seeding.md) — using factories in seeders.
- [Testing](database-testing.md) — using factories in tests.
- [Relationships](arvent-relationships.md) — wiring related factories.

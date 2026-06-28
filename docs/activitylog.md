# Activity Log (audit trail)

Keep a log of what happened in your app — who did what, to which record, and what changed. It's
your **audit trail** (every model create/update/delete, with the old and new values) *and* a
general **activity stream** (free-form events like "user logged in" or "report exported"), in one
table.

Activities are rows in the `activity_log` table (the `Activity` model), written either by the fluent
`activity()` logger or automatically by the `LogsActivity` model mixin.

## Logging an activity

```python
from arvel.activitylog import activity

await activity().log("Subscription renewed")

await (activity("billing")                       # a named log
    .caused_by(current_user)                     # who did it   (defaults to the auth user)
    .performed_on(invoice)                        # what it's about
    .with_properties({"amount": 4200})            # any extra data
    .log("Invoice paid"))
```

Each call writes one row with a `log_name`, `description`, optional `subject`
(`performed_on`), `causer` (`caused_by`, defaulting to the authenticated user), an `event`, and a
free-form `properties` dict.

## Auditing a model automatically

Mix in `LogsActivity` — **before** `Model` (Python MRO) — and every create, update, and delete is
logged for you, with the changed attributes captured in `properties`:

```python
from arvel import Model
from arvel.activitylog import LogsActivity

class Post(LogsActivity, Model):
    __fields__   = {"title": str, "body": str}
    __fillable__ = ["title", "body"]

post = await Post.create(title="Hello", body="…")   # logs event="created"
post.title = "Hi"
await post.save()                                    # logs event="updated"
await post.delete()                                  # logs event="deleted"
```

The update activity records exactly what changed:

```python
audit = await Activity.where(event="updated").first()
audit.changes()
# {"old": {"title": "Hello"}, "attributes": {"title": "Hi"}}
```

### Configuring what's logged

Set class attributes on the model:

| Attribute | Default | Effect |
|-----------|---------|--------|
| `__log_name__` | `"default"` | the activity's `log_name` |
| `__logs_events__` | `("created", "updated", "deleted")` | which events to record |
| `__log_attributes__` | `["*"]` | which fields to capture (`["*"]` = all) |
| `__log_only_dirty__` | `True` | updates record only changed fields, and skip an update that changed nothing |

```python
class Post(LogsActivity, Model):
    __log_name__       = "content"
    __log_attributes__ = ["title", "published"]   # ignore body churn
    __logs_events__    = ("updated", "deleted")   # don't log creation
```

## Reading the log

`Activity` is an ordinary model, so query it like any other:

```python
await Activity.where(log_name="billing").get()
await Activity.where(subject_type="Post", subject_id=post.id).get()   # this record's history
await Activity.where(causer_id=user.id).get()                         # everything a user did
```

Each row stores `subject_type`/`subject_id` and `causer_type`/`causer_id` so you can trace an
activity back to the record it touched and the user who caused it.

!!! note "Create the table"
    Add an `activity_log` table in a migration (`Activity.__table__` describes its columns):
    a `log_name`, `description`, polymorphic `subject_*`/`causer_*`, an `event`, and a JSON
    `properties` column.

## Common mistakes & gotchas

- **Mixing `LogsActivity` after `Model`.** Like `Searchable`, it must come **first**
  (`class Post(LogsActivity, Model)`), or the save/delete hooks are shadowed and nothing is logged.
- **Expecting a causer outside a request.** The causer defaults to the current authenticated user;
  in a job or CLI script there isn't one, so set it explicitly with `activity().caused_by(user)`.
- **Logging too much.** By default every changed attribute is recorded. Set `__log_attributes__`
  (and keep `__log_only_dirty__`) so the log captures the fields you care about, not every column —
  and so an update that changed nothing doesn't write a row.
- **Treating it as a queue.** The activity log is a *record*, not a task list — heavy reactions to an
  event belong on the [queue](queues.md) or in an [event](events.md) listener, not the log row.

## How it works

`LogsActivity` hooks the model lifecycle. Because arvel resets a model's originals *before* the
`saved` hook runs, the mixin snapshots the dirty/original values during **`saving`**, then on
`saved` writes an `Activity` with `event` `created`/`updated` and `properties = {old, attributes}`;
a delete writes a `deleted` row. The fluent `activity()` builds the same `Activity` row directly,
resolving the causer from the authenticated user unless you override it. Everything lands in one
`activity_log` table, which is why a single query can read a record's whole history or everything a
user did.

## See also

- [Database & ORM](database/index.md) — the models you audit, and their change-tracking (`get_dirty`,
  `get_original`) that `LogsActivity` builds on.
- [Search](search.md) — the other model mixin (`Searchable`); same "mix in before `Model`" rule.

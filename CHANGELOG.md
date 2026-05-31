# Changelog

All notable changes to **Arvel** are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Until `1.0.0`,
`0.x` releases may include breaking changes between minor versions.

---

## [Unreleased]

### Added

- **Recursive tree relations**: self-referential `descendants` / `ancestors`
  relations declared as zero-arg accessors (`has_many_recursive` /
  `belongs_to_recursive`). Lazy `.get()` returns the flat subtree and
  `.as_tree()` assembles a `TreeNode` forest, each from a single recursive CTE.
  `with_tree()` eager-loads the whole forest for a result set in one adjacency
  CTE (no N+1), with optional `constraint` and `max_depth` pushed down to SQL.
  When the model declares a self-referential `children` relation, `with_tree`
  hydrates it in place so the loaded subtree is walkable as plain models
  (`node.children[i].children`) synchronously — no `as_tree()` call and no extra
  query. `where_has` / `with_count` over a recursive relation raise a clear error.
- **Base Collection lookups and set operations**: `Collection.find`,
  `Collection.only`, and `Collection.except_` now live on the base collection
  (comparing members by value), completing the `contains`/`diff`/`intersect`
  family. `ModelCollection` overrides all of them to key off the primary key.
- **Critical framework bug-fix closure** (Epic 043 — WI-arvel-076): event
  listener dispatch now resolves provider-created listeners through the
  application container, and queued `ListenerJob` uses the bound event
  dispatcher for listener DI. Added regression coverage for provider wiring,
  queued listener DI, scheduler interrupt syntax, and controller DI resolution
  failures.
- **Security gate cleanup** (WI-arvel-076): normalized source `# nosec`
  suppressions so Bandit emits zero parser warnings, and added a narrow
  Gitleaks allowlist for fake `/secret` SSRF test URLs in the `arvel-image`
  parity suite.
- **Queue failed-job persistence wiring** (Epic 047 Story 5 — WI-arvel-077):
  `QueueServiceProvider.commands()` now passes the configured `FailedJobStore`
  into provider-created `queue:work` commands, so exhausted jobs can persist to
  `failed_jobs` in the real CLI path.
- **JWT secret and claim alignment** (Epic 047 Stories 2-3 — WI-arvel-078):
  `AuthServiceProvider` now rejects missing or short `jwt.secret` values before
  registering auth services, and passes configured algorithm, issuer, and
  audience through both `AuthService` and `JwtGuard`. The published auth config
  reads `JWT_SECRET` explicitly.
- **NotificationJob notifiable re-fetch** (Epic 047 Story 4 — WI-arvel-079):
  queued notification jobs now re-fetch the notifiable by class and ID on the
  worker side and deliver with `send_now()`, so stale queue payload state cannot
  trigger a second queue dispatch or spoof the notification target.
- **Queue retry attempt reset verification** (Epic 047 Story 6 — WI-arvel-080):
  confirmed the existing `queue:retry` path resets failed-job envelopes to
  `attempts=0` before re-dispatch, preserving the full retry budget.
- **Queue worker timeout logging** (Epic 047 Story 7 — WI-arvel-081):
  worker timeout handling now emits a structured `queue.job.timeout` warning
  with the job class and timeout before retrying or moving the job to DLQ.
- **Queue backoff and retry deadline verification** (Epic 047 Story 8 — WI-arvel-082):
  confirmed `Job.backoff`, per-attempt backoff lists, and `retry_until` behavior
  through the queue reliability regression suite.
- **Database queue app DB wiring** (Epic 047 Story 9 — WI-arvel-083):
  `QueueServiceProvider` now passes the application `AsyncEngine` and
  `async_sessionmaker` into `QueueManager`, so the database queue driver uses
  the configured app database instead of creating an isolated in-memory engine.
  The pop query uses `FOR UPDATE SKIP LOCKED` on PostgreSQL to prevent
  concurrent workers from claiming the same job.
- **HTTP consistency closure** (Epic 047 Stories 10-13 — WI-arvel-084):
  verified the default HTTP error envelope, typed `abort()` codes, automatic
  request scope middleware, and catch-all 500 handling through the existing
  HTTP consistency regression suite.
- **Cache correctness closure** (Epic 047 Stories 14-16 — WI-arvel-085):
  Redis-backed cache locks now use atomic `SET NX EX` acquisition and a
  token-checked Lua release path. Redis flush remains SCAN-based, and cache
  `has()` treats cached falsy values as present across the covered stores.
- **Auth authorization closure** (Epic 047 Stories 17-19 — WI-arvel-086):
  `CanMiddleware` can now resolve the singleton `Gate` from the request
  container and pass a route parameter into ability checks. The existing
  `Gate` and `Policy` suites verify singleton registration plus sync and async
  policy methods.
- **Session guard password verification closure** (Epic 047 Story 1 — WI-arvel-087):
  verified that `SessionGuard.attempt()` checks the submitted password hash
  before login, fails closed on unknown users or wrong passwords, and keeps the
  provider lookup side-effect free.

- **Conditional `sometimes` validation** (Epic 049 Story 15 — WI-arvel-075):
  ``Validator.sometimes()`` and ``Rule.sometimes()`` apply rules only when a
  callback returns ``True``. Pipe notation chains rules
  (``required|digits:16``). ``FormRequest.with_validator()`` registers
  conditional rules before ``rules()`` runs. Added ``required`` and ``digits``
  rule handlers.

- **Laravel-style validation rules** (Epic 049 Story 14 — WI-arvel-074): new
  ``arvel.validation`` module with ``Validator`` and string rules
  ``exists``, ``unique``, ``mimes``, and ``dimensions``. ``FormRequest``
  subclasses can declare ``rules()``, ``messages()``, and ``attributes()``;
  rules run after Pydantic parsing and before ``authorize()``.

- **`Model.observe(ObserverClass)`** (Epic 049 Story 9 — WI-arvel-073): pass an
  observer class instead of an instance. Resolved through the app container
  when ``DatabaseServiceProvider`` has booted (constructor DI); falls back
  to no-arg instantiation in tests. ``configure_observer_container()``
  binds the container.

- **Cancellable model lifecycle hooks** (Epic 049 Story 8 — WI-arvel-072):
  `creating` / `updating` / `deleting` fire before flush on `create()`,
  `save()`, and `delete()`. Return `False` (sync or async) to abort;
  raises `OperationCancelledError`. `updated` and `deleted` fire after
  successful flush. `clear_observers(model_cls)` resets registrations
  (mainly for tests).

- **Constrained eager loading on `QueryBuilder.with_()`**
  (Epic 049 Story 3 — WI-arvel-071): pass
  ``{"relation": lambda q: q.where(...)}`` alongside plain string paths.
  Callbacks receive a ``QueryBuilder`` for the related model; their
  ``WHERE`` clauses apply to the select-in load query via SQLAlchemy
  ``relationship.and_()``. Query-count tests pin the N+1 contract (base +
  one query per relation for ``has_many`` / ``belongs_to``).

- **`JsonResource.response()` / `ResourceCollection.response()`**
  (Epic 049 Story 7 follow-up — WI-arvel-070): build a Starlette
  ``ResourceResponse`` (``JSONResponse`` subclass) from ``to_dict(request)``.
  Handlers can ``return UserResource.collection(page).response(request)``
  with optional ``status_code`` and ``headers``. Closes Story 7
  Response-compat AC.

- **`has()` / `where_has()` / `doesnt_have()` for `BelongsToMany`**
  (Epic 049 Story 6 — WI-arvel-069): existence filters now resolve
  `BelongsToMany` descriptors (pivot-table joins) in addition to
  SQLAlchemy `relationship()` FK pairs. Constrained callbacks work on
  the related model inside the pivot join. New public helpers:
  `BelongsToMany.link_spec()`, `BelongsToManyLink`, and read-only
  pivot metadata properties on `BelongsToMany`; `QueryBuilder.statement`
  exposes the underlying `Select` for subquery composition.

- **Write-path `__casts__` coercion** (Epic 049 Story 10 follow-up —
  WI-arvel-068): assignment and construction now run the same
  `_CAST_DISPATCH` table as reads. `model.published_at = "2026-05-25T01:30:00Z"`
  stores a tz-aware UTC `datetime`; `Model(published_at=...)` does the
  same via `__setattr__`. `None` bypasses the cast. Invalid input raises
  `CastError` at assignment/construction (fail-fast), not on first read.
  JSON collection casts (`dict`, `list`, `array`) stay read-path only on
  write — coercing to Python collections breaks String-column INSERTs.
  Subclasses inherit parent `__casts__` on the write path too.

- **`JsonResource.additional({...})` / `ResourceCollection.additional({...})`**
  (Epic 049 Story 7 follow-up — WI-arvel-067): merge extra root-level
  keys into the response envelope. Works on both list-backed and
  paginator-backed collections. Extras merge AFTER the default body
  (or the paginator's `{data, meta, links}` envelope), so caller-
  supplied keys win on clash. Chainable — returns `Self`.

- **Programmatic global-scope API** (Epic 049 Story 2 — WI-arvel-066):
  register, inherit, and remove global scopes without editing
  `__arvel_global_scopes__` by hand.
  - `Model.add_global_scope(name, scope)` registers either a callable
    `(QueryBuilder) -> QueryBuilder` or a `GlobalScope` instance. The
    scope is stored on the model's own `__arvel_global_scopes__` —
    sibling classes and parents are not mutated.
  - `SoftDeleteScope` is now a public `GlobalScope` subclass.
    `SoftDeletes` registers `SoftDeleteScope("deleted_at")` (or your
    `__arvel_soft_delete_column__`) on every concrete subclass instead
    of an anonymous closure.
  - Subclasses inherit a parent's global scopes through normal MRO
    attribute lookup; the first call to `add_global_scope` on the
    subclass shallow-copies the inherited dict so the parent stays
    untouched.
  - New public read-only property `QueryBuilder.model` returns the
    model class the builder targets — meant for `GlobalScope.apply`
    implementations that need to resolve a column off the model.

- **Local query scopes — `scope_*` auto-discovery** (Epic 049 Story 1 —
  WI-arvel-065): define `scope_active(self, query)` on a model and call
  it as `Post.active()` or `Post.query().active()` without a decorator.
  - Discovery happens at attribute-lookup time via
    `_ModelMeta.__getattr__` (class-level) and
    `QueryBuilder.__getattr__` (qb-level). Both walk the model's MRO
    for a `scope_{name}` method.
  - Three signatures are supported and dispatched accordingly:
    - regular function `def scope_active(self, query)` — `self` is a
      bare instance via `object.__new__(cls)` (no DB state, no
      SQLAlchemy instrumentation)
    - `@staticmethod def scope_active(query)` — called bare
    - `@classmethod def scope_active(cls, query)` — receives the model
      class
  - Chains arbitrarily — `Post.active().published().limit(10).get()`
    works on both `Model.query()` entries and relationship builders.
  - The explicit `@scope` decorator is still supported for users who
    want to mark scope methods explicitly.
  - New public helper `arvel.database.model.unwrap_method(raw)` —
    returns the underlying function for a `staticmethod`/`classmethod`
    or `raw` itself. Useful for any framework code that needs to
    dispatch on the three method flavours.

- **`JsonResource.collection(paginator)` integration** (Epic 049 Story 7 —
  WI-arvel-064): the `collection()` factory now accepts any of Arvel's
  paginators in addition to a plain list. With a paginator the response
  envelope flips from `{data: [...]}` to the paginator's full
  `{data, meta, links}` shape, each item still transformed through the
  resource class.
  - URL-aware Starlette/FastAPI requests get HATEOAS-style links
    automatically — `request.url.{scheme,netloc,path}` is the base, and
    `request.query_params` (sans `page` / `cursor`) is merged so filters
    and sort flags survive pagination.
  - Dummy/headless requests fall through to integer page numbers.
  - `SimplePaginator` returns `{prev, next}` only; `CursorPaginator`
    emits a single `next` URL whose query carries the opaque cursor.
  - New public `arvel.http.Paginatable` Protocol — a structural type
    that lets `arvel.http` stay decoupled from `arvel.database`
    (ADR-016). Any object with `items: list[T]` and the standard
    `to_dict(items_serializer=, base_url=, query=)` signature works.
  - `CursorPaginator.to_dict()` now accepts `base_url` / `query` and
    builds URLs via the new `arvel.database.paginator.build_cursor_url`
    helper. Without `base_url` it keeps returning the raw cursor token
    (backward compatible).
  - `ResourceCollection.__init__` grew an optional `paginator=` kwarg
    so external callers can construct paginator-backed collections
    directly.

- **`datetime` / `date` / `timestamp` casts** (Epic 049 Story 10 — WI-arvel-063):
  `__casts__` learned three temporal entries. All three normalise to UTC and
  raise `CastError` (a new `ORMError` subclass) on unparseable input — so
  apps can hook 400 vs 500 via the `HttpServiceProvider`'s exception
  translator registry from WI-arvel-061.
  - `datetime`: accepts ISO-8601 strings (including bare `Z` and `+HH:MM`
    offsets), epoch seconds (`int` or `float`), and `datetime` instances.
    Returns a tz-aware `datetime` in UTC. Naive datetimes are *assumed* to
    be UTC — no local-time guesswork.
  - `date`: accepts ISO `YYYY-MM-DD`, ISO datetime strings, `datetime`/`date`
    instances, and epoch seconds. Returns a `date` using the UTC calendar
    day.
  - `timestamp`: accepts ISO strings, `datetime`, and epoch numerics.
    Returns an `int` of epoch seconds (UTC). `bool` is rejected explicitly
    (it's an `int` subclass but `True`/`False` as epochs is almost certainly
    a bug).
  - New public `arvel.database.exceptions.CastError` carries `cast_type:
    str` and `value: object` for translator wiring.

- **`Paginator.links()` and HATEOAS-style `to_dict()` URLs** (Epic 049 Story 16 —
  WI-arvel-062): paginators can now build the full `{first, prev, next, last}`
  URL block instead of leaving callers to glue page numbers onto a base URL.
  - `Paginator.links(base_url, *, query=None) → dict[str, str | None]` returns
    every link as a fully-encoded URL. Filters and sorts passed via `query` are
    merged into every URL; the paginator always owns the `page` key.
  - `SimplePaginator.links(...)` returns just `{prev, next}` — total is
    unknown so `first`/`last` aren't computable.
  - `Paginator.to_dict(base_url=..., query=...)` / `SimplePaginator.to_dict(...)`
    now emit URL strings under `links` when `base_url` is supplied. Without it
    they keep returning integer page numbers (backward compatible).
  - New `arvel.database.paginator.build_page_url(base_url, page, query=None)`
    helper composes a URL with `page=N` merged into the query string, normalises
    trailing-slash paths, and preserves any caller-supplied query params.
  - `SimplePaginator` and `CursorPaginator`'s generic parameter is no longer
    bound to `QueryMixin` — the standalone containers accept any item type.

- **`ModelNotFoundError` → HTTP 404 mapping** (Epic 049 Story 4 — WI-arvel-061):
  `Model.find_or_fail()` and `QueryBuilder.first_or_fail()` now surface as the
  standard 404 envelope instead of an unhandled 500. The mapping is wired by
  the `HttpServiceProvider` via a new exception-translator hook on
  `HttpExceptionHandler` — the HTTP layer itself stays free of ORM imports so
  ADR-016's layering rule still holds.

  - `HttpExceptionHandler(*, translators=...)` and `add_translator(exc_type,
    translator)` let providers (or app code) register foreign-exception ➜
    `HttpException` mappings.
  - `ProblemDetailsHandler` honours the same translator registry, so RFC 7807
    responses get the 404 envelope too.
  - `arvel.providers.http_provider.default_translators()` is the canonical
    wire-up: it imports `ModelNotFoundError` lazily so apps using the HTTP
    layer without the ORM still boot.

### Changed

- **CI warning cleanup**: disposed direct SQLite engines in console, database,
  notification, and queue tests so `make ci` now exits with no
  `ResourceWarning` output or warning summary.

- **Removed all `# noqa: FBT002` suppressions from console commands** (FB-060-002):
  Converted every boolean flag in `_callback` inner functions to a keyword-only
  parameter (added `*,` before the first `bool` option) across 11 files:
  `_base_make.py`, `key_generate.py`, `key_rotate.py`, `make_migration.py`,
  `make_model.py`, `new.py`, `openapi_export.py`, `serve.py`, `shell.py`,
  `storage_link.py`, `queue/commands/queue_work.py`. Typer still reads the
  decorated signatures correctly — keyword-only `_Option(...)` params work
  identically from the CLI. Zero `# noqa: FBT002` directives remain in `src/`.

- **Corrected aspirational API examples in site docs** (FB-052-002):
  Four pages documented methods that don't exist yet:
  - `facades.md`: replaced `Bus.fake()`, `Notification.fake()`, `Mail.assert_sent()`,
    and `Bus.assert_dispatched()` (none implemented) with working `Mail.fake()` /
    `Event.fake()` / `Cache.fake()` / `Storage.fake()` examples and accurate
    `fake()` support table. Corrected `Cache` row from ⚠️ to ✅ — `Cache.fake()`
    is fully implemented.
  - `mail.md`: replaced `Mail.assert_sent()` / `Mail.assert_to()` with the real
    `driver = Mail.fake()` / `driver.sent` list API.
  - `queues.md`: replaced `Bus.fake()` + `Bus.assert_dispatched()` with the
    working direct-handler test pattern + `Mail.fake()` for mail assertions.
  - `notifications.md`: replaced `N.fake()` / `N.assert_sent_to()` block with
    the correct `Mail.fake()` approach for mail notifications, and a note about
    channel spy patterns for other channels.

- **Added end-to-end "Putting it together" tutorial in `controllers.md`** (FB-060-003):
  Three-step narrative — scaffold with `make:controller --resource --model=Post`,
  register with `Route.resource()`, inspect with `arvel route:list` — showing
  how WIs 055/058/059/060 compose into a complete resource feature.

### Added

- **`make:controller --resource` scaffold** (Epic 048 Story 10 — WI-arvel-060):
  `arvel make:controller PostController --resource` writes
  `app/http/controllers/post_controller.py` with all seven RESTful method
  stubs (`index`, `create`, `store`, `show`, `edit`, `update`, `destroy`),
  each raising `NotImplementedError` so the gap is loud the moment a route
  hits an unimplemented action. Two further switches:
  - `--api` drops the two HTML-form methods (`create`, `edit`) — mirrors
    `Route.api_resource()`.
  - `--model=Post` adds `from app.models.post import Post` and types the
    member-method parameter as `post: Post` instead of `id: int`, so
    [implicit model binding](docs/site/docs/routing.md#route-model-binding)
    resolves it automatically.

  Both flags require `--resource`. All generated files pass `ruff format`,
  `ruff check`, and `mypy --strict` immediately — no post-generation
  cleanup. The default `make:controller` (no `--resource`) still emits
  the original five-action template, so existing scripts are unaffected.

  Internal change worth noting: `BaseMakeCommand._validate_name` is now
  the public `validate_name` (sibling commands needed it). 18 new tests
  under `packages/arvel/tests/console/test_wi060_make_controller_resource.py`
  cover every flag combination plus generated-file linting.

- **`route:list` console command upgraded to Laravel parity** (Epic 048 Story 9 — WI-arvel-059):
  `arvel route:list` now prints a five-column table — Method, URI, Name,
  Action, Middleware — instead of the old three-column Method/Path/Handler
  view. Two new switches:
  - `--filter <substring>` filters routes whose path contains the substring
    (case-insensitive).
  - `--json` emits a JSON array (one object per route with `method`, `path`,
    `name`, `action`, and `middleware` fields) for piping into `jq`.

  The Action column renders as `Controller#method` for controller routes,
  `Controller#__call__` for invokable controllers, and the handler's
  `__qualname__` for plain function handlers. Middleware shows comma-joined
  class names, or `-` when the route has none. `RouteListCommand.get_routes()`
  prefers the container-bound `Router` (honouring the WI-021 contract) and
  falls back to `Router.singleton()` when the application isn't bootstrapped
  — useful in test contexts. 20 new tests under
  `packages/arvel/tests/console/test_wi059_route_list.py`. Docs updated:
  `docs/site/docs/console.md` (new flags), `docs/site/docs/controllers.md`
  (new "Inspecting your routes" section), `docs/api/http-api.md` (new
  `RouteListCommand` entry). Closes the deferred AC on Epic 048 Story 3
  (resource routes appear in `route:list`).

- **`Route.resource()` macro for RESTful controllers** (Epic 048 Story 3 — WI-arvel-058):
  `Route.resource("/posts", PostController)` registers the seven canonical
  CRUD routes — `index`, `create`, `store`, `show`, `edit`, `update`,
  `destroy` — with conventional paths and named routes (`posts.index`,
  `posts.show`, ...). Member routes use a singular path parameter
  (`/posts/{post}`) so [implicit model binding](docs/site/docs/routing.md#route-model-binding)
  resolves them automatically. A heuristic singulariser covers common
  English plurals (`/posts` → `{post}`, `/categories` → `{category}`,
  `/boxes` → `{box}`); use `parameter=` to override when the rule is
  wrong. The returned `ResourceRegistration` builder chains `.only(...)`,
  `.except_(...)`, and `.names({...})` for selective registration and
  name overrides. `Route.api_resource()` is the JSON-only shortcut that
  drops `create` and `edit`. Resource registration composes with
  `Route.group(...)` and per-route middleware. 19 new tests under
  `packages/arvel/tests/routing/test_wi058_route_resource.py`. Docs
  updated: `docs/site/docs/controllers.md` (rewritten resource-controller
  section with composition examples), `docs/api/http-api.md` (new
  `Route.resource`, `Route.api_resource`, and `ResourceRegistration`
  entries). Closes Epic 048 Story 4's deferred AC (resource routes follow
  Laravel's naming convention).

- **Method-based controller routing with DI** (Epic 048 Story 5 — WI-arvel-057):
  `Route.get("/posts/{post}", controller=PostController, action="show")` now
  resolves `PostController` through the [container](docs/site/docs/container.md)
  and dispatches to the named method. Constructor dependencies are injected
  automatically — `def __init__(self, repo: PostRepository)` gets a fresh
  `PostRepository` (or a shared singleton, depending on how it's bound). The
  bound method's signature flows through to FastAPI as-is, so the new dispatch
  composes cleanly with [implicit model binding](docs/site/docs/routing.md#route-model-binding),
  [`FormRequest`](docs/site/docs/requests.md), and ordinary path / query / body
  params. Both controller forms — method-based (`controller=` + `action=`) and
  invokable (`controller=` alone, with `async __call__`) — register eagerly:
  the throwaway trailing `(Cls)` call is gone for good. Binding a controller
  with neither `action=` nor `__call__` now raises a clear `TypeError` at
  decoration time, not at `Router.register_with_app` time, so misuse surfaces
  immediately. New `arvel.routing.MethodControllerAdapter` is exported so
  apps wiring FastAPI themselves can build the same adapters. 12 new tests
  under `packages/arvel/tests/routing/test_wi057_controller_di.py`. Docs
  updated: `docs/site/docs/controllers.md` (added DI / dispatch notes),
  `docs/api/http-api.md` (new `MethodControllerAdapter` entry).

- **Explicit route model binding** (Epic 048 Story 2 — WI-arvel-056):
  new `Route.bind(name, resolver)` registers a custom async resolver
  keyed by URL parameter name. Outside any `Route.group()` block the
  resolver applies globally; inside a group it's scoped to that group
  and nested groups can override it. The resolver receives the raw URL
  string and runs at request time — returning `None` raises
  `NotFoundException` (404), same path as implicit binding. Explicit
  resolvers always win over implicit `Model` binding when both could
  apply, and the resolver's return value isn't constrained to be a
  `Model` instance (so you can bind opaque tokens, soft-deleted records
  with `Post.with_trashed().find(...)`, or anything else). New
  `Router.bindings()` exposes a snapshot of the global resolvers. 8 new
  tests under `packages/arvel/tests/routing/test_wi056_explicit_binding.py`.

- **Implicit route model binding** (Epic 048 Story 1 — WI-arvel-055):
  type a path parameter with a `Model` subclass and Arvel resolves the row
  from the database before the handler runs. `@Route.get("/posts/{post}")`
  with `async def show(post: Post)` now produces a loaded `Post` instance —
  no manual `find_or_fail` calls — and a miss returns `404 NOT_FOUND`
  through the standard `HttpExceptionHandler` envelope. Custom binding
  columns are supported via `Model.route_key_name`
  (e.g. `route_key_name: ClassVar[str] = "slug"`), in which case the lookup
  goes through `Model.where(<key>=<value>).first()` so global query
  scopes (soft-delete, multi-tenant) still apply. New
  `arvel.routing.ImplicitRouteModelBinder` class is registered automatically
  by `Router.register_with_app`; exposed publicly so apps that wire FastAPI
  themselves can introspect or unit-test the binding logic. 12 new tests
  under `packages/arvel/tests/routing/test_wi055_route_model_binding.py`.
  Docs updated: `docs/site/docs/routing.md` (new "Route model binding"
  section), `docs/api/http-api.md` (new `ImplicitRouteModelBinder` entry),
  `docs/api/database-api.md` (documented `route_key_name` on `ActiveRecord`).

### Fixed

- **`Model.where_pivot()` class-level shortcut** (FB-060-001): the
  WI-arvel-060 changeset moved `tests/database/test_012_s3_relationships.py`
  from `UserS3.query().where_pivot(...)` to the bare `UserS3.where_pivot(...)`
  form (matching Laravel's `__callStatic` ergonomics), but the supporting
  classmethod hadn't landed on `QueryMixin` yet, so the test failed with
  `AttributeError`. Added `QueryMixin.where_pivot()` that forwards to
  `cls.query().where_pivot(...)`; the plain `QueryBuilder` still raises
  `RuntimeError`, which is exactly what the test asserts. No effect on
  `BelongsToMany` accessors — they retain their own working override.

### Changed

- **Pyright strict-mode debt cleanup** (WI-arvel-054): cleared the entire
  inherited backlog of 125 strict-mode pyright errors across 21 files
  (carried over from WIs 044/045/047/050/052/053). All three type checkers —
  mypy, pyright (strict), and ruff — now report zero errors and zero
  warnings across `packages/arvel`, `packages/arvel-permission`, and
  `packages/arvel-image`. Source-level changes that are visible to consumers:
  promoted internal helpers from underscore-prefixed to public — `JsonB` and
  `PendingColumn` on `arvel.database.schema`, `matches_wildcard` and
  `apply_wildcard_config` on `arvel_permission.traits`, `resolve_path_generator`
  in `arvel_image.media`, plus a `JwtGuard.secret_or_key` read-only property and
  a public `arvel_permission.events.clear_listeners()` helper for test isolation.
  Composite-PK normalisation is now a typed `_coerce_pk_to_tuple()` helper in
  `arvel.database.model` and `arvel.database.query`. No public API behaviour
  changed.

### Added

- **Routing security & UX polish** (Epic 048 stories 4 / 6 / 7 / 8 —
  WI-arvel-053): `name_prefix` parameter on `Route.group()` stacks
  route-name prefixes the same way `prefix` stacks paths; new
  `arvel.routing.RoutingError` (a `ValueError` subclass) is raised on
  missing route parameters or missing `APP_URL`; new `arvel.routing.url()`
  helper resolves any path against `APP_URL`; `route()` gains an
  `absolute=True` kwarg; new `URL` facade exposes
  `URL.signed_route(name, expires_at=..., **params)` and
  `URL.has_valid_signature(request)` for tamper-proof, optionally
  time-limited links (HMAC-SHA256 over `APP_KEY`,
  `hmac.compare_digest` verification, Laravel-compatible `base64:`
  prefix); new `MethodSpoofMiddleware` rewrites POSTs with
  `_method=PUT|PATCH|DELETE` for HTML form parity; new `SignedMiddleware`
  aborts requests with invalid signatures (403). 33 new tests under
  `packages/arvel/tests/routing/test_wi053_routing_polish.py`.
- **`Str` and `Arr` Laravel-parity facade classes** (`arvel.support.Str`,
  `arvel.support.Arr`; also re-exported from `arvel`). `Str` covers
  slug/headline, UUID/word-count predicates, limit/pad, starts/ends/contains,
  after/before/between, and cryptographically secure `Str.random()` /
  `Str.password()` generators. `Arr` covers first/last with predicates,
  flatten with depth, only/except, dot/undot, get/set/has dot-notation
  traversal over `Mapping[str, object]`, pluck (dict-shaped or
  object-shaped items), wrap, prepend, where, divide, and a cryptographic
  `Arr.shuffle()` (Fisher-Yates on `secrets.randbelow`). Closes Epic 049
  stories 11–13. Tests: `packages/arvel/tests/support/test_str_facade.py`
  (61) and `test_arr_facade.py` (50).
- Doc rewrites: `docs/site/docs/strings.md` and `docs/site/docs/helpers.md`
  now describe the real `Str`/`Arr` surface (previous content referenced an
  aspirational `arvel.support.helpers` module that never shipped).

### Changed

- **Single binary: the `arvel-cli` package and the `arvel-new` console
  script are gone — `arvel new <app>` is now the canonical entry point.**
  The scaffolder (name validation, templating, the packaged skeleton
  tree, and the Typer command) merged into `arvel` itself. One install
  (`uv tool install arvel`), one binary, one mental model. The skeleton
  moved to `arvel._skeleton` (loaded via `importlib.resources`); the
  scaffolding helpers live under `arvel.console._scaffold`; the command
  is `arvel.console.commands.new:NewCommand`. The dual-binary split was
  ADR-069's resolution to a console-script collision; ADR-075 supersedes
  it now that the merge avoids the collision entirely. No backward-compat
  shim — `arvel-new my-app` becomes `arvel new my-app`. Users who
  installed `arvel-cli` should `uv tool uninstall arvel-cli` then
  `uv tool install arvel`.
- **`make:*` stub generators now produce framework-aware code instead of
  Laravel-shaped placeholders.** Every class-based generator targets a
  real Arvel primitive and normalizes its argument with `pascal_case`,
  so `make:foo welcome_mail`, `make:foo WelcomeMail`, and
  `make:foo welcomeMail` all generate `class WelcomeMail`.
  - `make:controller` subclasses `arvel.Controller` with `Request`-typed
    handlers (`index`, `show`, `store`, `update`, `destroy`).
  - `make:model` produces a SQLAlchemy declarative model with
    `Mapped[...]` columns, `__tablename__`, and the `Timestamps` mixin.
  - `make:request` generates `FormRequest[Payload]` with a paired
    Pydantic body schema and an async `authorize()`.
  - `make:seeder` subclasses `arvel.database.Seeder`.
  - `make:factory` subclasses `Factory[T]` with a commented `model = ...`
    binding.
  - `make:resource` subclasses `JsonResource[T]` with `to_dict()` (the
    previous `to_array()` was Laravel-shaped and never matched the
    framework API).
  - `make:test` emits a pytest function test using
    `bootstrap.app.create_application()` + Starlette's `TestClient`,
    written to `tests/feature/` (was `tests/Feature/`).
  - `make:view` extends `layouts/base.html` to slot into a shared layout.
- **`make:request` now writes to `app/http/requests/`** (was
  `app/Http/Requests/`) to match the skeleton's lowercase path convention.

### Removed

- **`make:scope` and `make:rule` retired.** Neither targeted a real
  framework primitive — Arvel's query scopes are declared with the
  `@scope` decorator on the model class (or as `GlobalScope` subclasses
  registered on `Model.__arvel_global_scopes__`), and there is no
  framework `Rule` base class. Both entry-points are removed.

### Added

- **Auth HTTP layer (`arvel.auth`) — WI-arvel-028.** Moves all authentication
  functionality into the framework core so apps don't ship auth boilerplate.
  - **`AuthController`** — REST endpoints for register, login, logout, token
    refresh, email verification (send + confirm), and password reset
    (request + complete). All inputs validated via Pydantic `FormRequest`.
  - **`CsrfDoubleSubmitMiddleware`** — enforces the double-submit cookie
    pattern on state-changing auth routes. Sets an `__Host-` prefixed cookie
    (HTTPOnly, SameSite=strict, Secure-on-HTTPS) and rejects requests whose
    `X-CSRF-TOKEN` header doesn't match.
  - **`ThrottleLoginMiddleware`** — rate-limits login attempts per
    `IP + email` key with a configurable sliding window (default 5 attempts /
    60 seconds). Returns `429 Too Many Requests` with `Retry-After` when the
    limit is exceeded.
  - **`VerifyEmailMailable` / `PasswordResetMailable`** — framework mailables
    in `arvel.auth.mail`. Signed URL generation is handled inside the
    mailable; no app code required.
  - **`AuthBroker`** — connects `Registered` and `PasswordResetRequested`
    events to `SendVerificationEmail` and `SendPasswordResetEmail` listeners.
    Auto-wired by `AuthServiceProvider`.
  - **`auth:install` command** — publishes auth config, migration stubs,
    User model stub, and route stub via four tagged publish groups
    (`config`, `migrations`, `models`, `routes`).

- **CLI parity: 30 new commands across make / maintenance / queue / db /
  introspection** (WI-023, PRD-023). Closes the parity gap with Laravel's
  Artisan for green-field workflows.
  - **Stub generators** — `make:cast`, `make:channel`, `make:command`,
    `make:event`, `make:job`, `make:listener`, `make:mail`, `make:middleware`,
    `make:notification`, `make:observer`, `make:policy`, `make:provider`,
    plus 4 migration generators: `make:cache-table`, `make:session-table`,
    `make:queue-table`, `make:queue-failed-table`. `cache:table` was
    removed in favour of `make:cache-table` (no compat shim — green-field
    rule).
  - **Migration family** — `migrate:fresh` (drop-all + re-run, optionally
    with `--seed`), `migrate:reset` (rollback all), `migrate:refresh`
    (rollback all + re-run, optionally with `--seed`). All three honour a
    production guard: `ARVEL_ENV=production` exits 2 unless
    `ARVEL_ALLOW_DESTRUCTIVE=1` is set.
  - **Maintenance mode** — `arvel down` writes
    `storage/framework/down`; `arvel up` removes it. A new
    `MaintenanceModeMiddleware` (auto-wired by `HttpServiceProvider` when
    `MaintenanceModeManager` is bound) responds 503 with optional
    `Retry-After` / `Refresh` headers, plus a bypass via cookie or
    `?bypass=<secret>` (256-bit token, constant-time compare,
    HttpOnly + SameSite=Lax + Secure-on-HTTPS). See ADR-072.
  - **Queue operations** — `queue:restart` signals workers to exit
    gracefully via a cache key (`arvel:queue:restart`, ADR-073);
    `Worker.run_until` polls each loop. `queue:clear <queue>` purges a
    queue. `queue:prune-failed --hours N` removes failed jobs older than N
    hours (Laravel parity).
  - **Database & app introspection** — `db:show`, `db:table <name>`,
    `model:show <FQN>`, `channel:list`, `event:list`. Includes new public
    accessors `EventDispatcher.all_listeners()` and
    `BroadcastManager.channels()` to power the listings.
  - **Aliases & shortcuts** — `tinker` → `shell`, `schedule:run` →
    `schedule:work --once`, `storage:unlink` (counterpart to
    `storage:link`), `auth:clear-resets` (deletes expired password reset
    tokens), `test` (runs `pytest.main` in-process — no subprocess).
- **`Migrator.drop_all()` and `Migrator.reset()`** on
  `arvel.database.migrator.Migrator`. `drop_all` uses a 3-pass retry loop
  to satisfy FK constraints without inspecting dialect-specific
  reflection metadata. Powers `migrate:fresh` / `migrate:reset` /
  `migrate:refresh`.
- **`Application.has_command(name)`** public method (WI-023). Returns
  whether a command name is registered in the parent `Application`.
- **`BaseMakeCommand` `_render(name)` override hook + name validation**
  (ADR-074). Generators subclass `BaseMakeCommand` and override
  `_render()` to produce framework-aware stubs instead of mining a
  shared `STUBS` table. Names are validated via
  `^[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z][A-Za-z0-9_]*)*$` (allows nested
  namespacing, rejects path traversal / shell meta / null bytes /
  fullwidth chars).
- **Real migration runner + seeder discovery** (WI-022, FR-022-001..014,
  SR-022-001). `arvel migrate`, `migrate:rollback`, `migrate:status`, and
  `db:seed` are no longer stubs — they wire to a new
  `arvel.database.migrator.Migrator` orchestrator that:
  - Auto-creates a Laravel-style `migrations` tracking table on first run
    (`migration` / `batch` / `applied_at`).
  - Discovers `*.py` files under `database/migrations/` (lexicographic order,
    `_`-prefixed files are skipped as helpers), and runs each pending
    migration's module-level `async def up(schema)` in its own transaction.
  - Stamps every applied migration with the current batch number, so
    `migrate:rollback` walks the most recent batch in reverse and calls each
    `down(schema)` — Laravel rollback semantics.
  - Stops at the first failing migration; earlier-applied migrations stay
    applied so you can fix-and-resume instead of starting over.
  - Surfaces `--dry-run` on `migrate` and a tabular `migrate:status` showing
    every discovered file with applied/pending + batch + applied-at.
  - Resolves seeders from `database/seeders/<snake>.py` with a strict
    allowlist (`^[A-Za-z][A-Za-z0-9_]*$`) on `--seeder` to prevent path
    traversal and shell-metacharacter injection.
  - Honest exit codes throughout: `0` = success, `1` = user-code error (a
    migration or seeder body raised), `2` = bootstrap or configuration error
    (no `Application`, no engine, missing directory, invalid `--seeder`).
- **`docs/site/docs/migrations.md` + `docs/site/docs/seeding.md`** updated to
  match the actual generator output (module-level `async def up(schema)`,
  not the previously-documented class-based shape that was never shipped).
  Adds an exit-codes table for each command.
- **CLI — framework `Application` bootstrap for commands that need DI**
  (WI-021, FR-021-18, FR-021-19, FR-021-10). New `arvel.console.bootstrap`
  module discovers the user's `bootstrap/app.py` by walking up to four
  ancestor directories from `cwd`, imports it, and calls
  `create_application()`. Commands opt in by declaring
  `needs_application: ClassVar[bool] = True` on the `Command` subclass;
  the entrypoint then binds the booted framework `Application` to
  `self.app` before invocation. `migrate*`, `db:seed`, `route:list`,
  `schedule:work`, `schedule:list`, and `shell` use this path. Commands
  outside a project still work for the entry-point-only subset (`about`,
  `--version`, `make:*`, etc.).
- **CLI — `Command.call(name, args=...)` and `Command.call_silently(...)`**
  (WI-021, FR-021-24). Cross-command invocation via the parent
  `Application`. Returns the called command's exit code unchanged.
- **CLI — expanded `Context` I/O surface** (WI-021, FR-021-23). Adds
  `warn()`, `comment()`, `alert()`, and `newline()` so commands can
  signal severity beyond plain `info` / `error`. Output goes to stderr
  for `warn`/`alert`, stdout for `comment`.
- **`arvel.console.Application.iter_commands()`** public accessor
  (WI-021). Yields every registered `Command` instance in registration
  order. Used by the entrypoint to honor `needs_application` without
  poking at `_commands`.
- **`make:migration <name>`** (WI-021, FR-021-20). Generates a
  timestamped migration stub in `database/migrations/`. The name is
  validated against `^[A-Za-z][A-Za-z0-9_]*$` to block path-traversal
  and docstring-breakout injection vectors before it is embedded in the
  filename or generated module docstring.
- **`serve`** (WI-021, FR-021-25). Runs `public.asgi:asgi` under uvicorn.
  Defaults to `127.0.0.1:8000` (loopback only — not `0.0.0.0`). Refuses
  to start outside an Arvel project context.
- **`key:generate`** (WI-021, FR-021-26). Generates a 256-bit
  `APP_KEY` via `secrets.token_bytes(32)`, base64-encoded. Writes/
  replaces the `APP_KEY=` line in `.env`; refuses to overwrite a
  populated key without `--force`. `--show` prints the key to stdout
  instead.
- **`queue:*` command Typer registration overrides** (WI-021,
  FR-021-12/13/14). `queue:work`, `queue:failed`, `queue:retry`,
  `queue:flush`, and `queue:forget` now own their Typer registration via
  `register()` and dispatch to public async methods (`run_worker`,
  `list_failed`, `retry`, `flush`, `forget`). `queue:work` uses
  `worker.drain_then_stop()` for a deterministic single-shot drain.

### Changed

- **CLI scaffolder script renamed `arvel` → `arvel-new`** (WI-021,
  P0-02). The project scaffolder previously shared the `arvel`
  console-script name with the runtime CLI, which broke whichever
  package was installed second. The scaffolder is now `arvel-new`;
  documentation (`README.md`, `docs/site/docs/installation.md`,
  `docs/strategy/constitution.md`) updated accordingly.
- **`cache:clear` and `cache:forget` now report real failures**
  (WI-021, FR-021-06/07/27). Previously swallowed exceptions and
  returned exit code 0. Errors now surface with a non-zero exit and
  the underlying message on stderr.
- **`key:rotate` now exits with code 2 and points at the tracking issue**
  (WI-021, FR-021-08, FB-022-002) instead of silently no-op'ing with
  exit code 0.
- **`schedule:work` / `schedule:list` honor the user's `Kernel.schedule`**
  (WI-021, FR-021-21) via the bootstrapped framework `Application` rather
  than running against an empty in-process kernel.
- **`shell` REPL namespace** (WI-021, FR-021-22) now exposes `app`,
  `container`, and the public facades (`Cache`, `Auth`, `Bus`, `Log`,
  `Config`) when the framework is bootstrapped. Falls back to stdlib
  `code.interact` when IPython is not installed.
- **`route:list` resolves the `Router` from the framework container**
  (WI-021, FR-021-05) instead of returning an empty list.
- **`discover_commands` widened to broad `Exception`** (WI-021,
  FR-021-17). One bad entry-point no longer masks the rest of the
  command table; failures are logged at WARN with type and message.

### Fixed

- **`LangServiceProvider` regression from WI-020** — `app.base_path` is
  a method on the framework `Application`, not an attribute. The
  provider now resolves it via a `_resolve_base_path` helper that
  handles both callable and attribute forms, fixing a `TypeError` that

- **CLI — built-in commands are now discovered via the `arvel.commands`
  entry-point group** (WI-020, FB-019-002). The 24 built-ins that used to
  live in a hardcoded list inside `arvel.console.entrypoint._get_commands()`
  are now declared in `[project.entry-points."arvel.commands"]` in
  `packages/arvel/pyproject.toml`. The entrypoint module shrinks to a one-
  liner over `discover_commands()`. `reverb:start` joins the entry-points
  table so it becomes reachable when the `[broadcasting]` extra is
  installed (and gracefully absent otherwise — the loader now tolerates
  `ImportError` from individual entry-points and continues). Third-party
  packages can ship `Command` subclasses by declaring their own
  `arvel.commands` entry-points; no patching of arvel needed.
- **CLI — `ConsoleServiceProvider` binds the console `Application` into
  the framework container** (WI-020, FB-019-001). A new
  `arvel.console.providers.ConsoleServiceProvider` walks every booted
  provider's `commands()` method and registers the returned commands on
  the bound `Application`. The `SchedulerServiceProvider` now auto-wires
  `SchedulerHooks.run_command` from this binding, so apps that register
  both providers get `Schedule.command("about").daily()` working without
  any hook plumbing. Apps that don't register `ConsoleServiceProvider`
  see `skipped: no_run_command_callback` for command tasks (other task
  types continue to work).
- **`Application.run(name, args=None) -> int`** on `arvel.console.Application`
  (WI-020, FR-020-01). Programmatic, in-process command invocation that
  bypasses Typer's CLI parsing. Raises `KeyError` for unknown commands and
  returns the command's exit code unchanged. Used by the scheduler hook;
  also available for embedding the CLI in custom drivers and tests.
- **`Application.register_command(cmd)`** for post-construction command
  registration (WI-020, FR-020-02). Re-registering an existing name
  overwrites and logs a warning — matches the constructor's collision
  behavior.
- **`Application.iter_providers()`** public accessor on the framework
  `Application` (WI-020, ARCH-020-B). Yields every registered
  `ServiceProvider` instance in registration order. Used by
  `ConsoleServiceProvider.boot()` to avoid touching `_provider_instances`.
- **Scheduler — `Schedule.job()` and `Schedule.command()` now actually
  dispatch** (WI-019, Gap-A). Previously both branches recorded a `skip`
  outcome with `kind:job` / `kind:command`. The kernel now accepts a
  `SchedulerHooks` bundle with optional `dispatch_job` and `run_command`
  callbacks. The `SchedulerServiceProvider` auto-wires `dispatch_job` to
  `Bus.dispatch(...)` when the queue subsystem is registered, so apps that
  register both `QueueServiceProvider` and `SchedulerServiceProvider` get
  cron-to-queue dispatch for free. Apps without `Bus` see
  `skipped: no_dispatch_job_callback`.
- **Poison-pill envelope audit logging** (WI-019, FB-018-002). The database,
  redis-direct, and taskiq drivers now emit a structured
  `queue.envelope.malformed` warning (via `structlog`) when a popped payload
  fails `JobEnvelope.from_json`. The worker still swallows the message so
  the loop stays alive — operators can now spot recurring corruption in logs
  instead of silent drops. Fields: `driver`, `queue`, `payload_size`,
  `exception_type`, `reason` (plus `row_id` for the database driver).
- **AMQP delay-plugin actionable error** (WI-019, FB-018-003). When
  `Job.delay > 0` is dispatched through `taskiq_aio_pika` and the broker
  doesn't have the `rabbitmq-delayed-message-exchange` plugin enabled, the
  upstream `IncorrectRoutingKeyError` is now re-raised as a `RuntimeError`
  carrying the install command:
  `rabbitmq-plugins enable rabbitmq_delayed_message_exchange`. The original
  exception is preserved as the cause. Unrelated broker errors pass through
  unwrapped, and `delay=0` jobs never trigger the wrapper.
- `RedisQueueConn` and `JobRow` are now public symbols of their respective
  driver modules (previously `_RedisQueueConn` and `_JobRow`) so test fakes
  and operator scripts can interact with the queue schema and the Redis
  Protocol without poking private internals.
- **Queue: AMQP broker support + first-class delay/priority** (WI-018) — every
  queued job can now declare a `delay` (int seconds or `timedelta`) and a
  `priority` (`0..9`, higher runs first) directly on the `Job` class, and
  `Bus.dispatch(job, delay=..., priority=...)` overrides them per call. All
  four drivers honour both fields natively:
  - **sync**: `await asyncio.sleep(delay)` before handling.
  - **database**: new `priority` column on the `jobs` table;
    `ORDER BY priority DESC, available_at ASC` for fair, prioritized pop.
  - **redis-direct**: composite design — `<key>:<q>:scheduled` ZSET (by
    `available_at_ms`) + `<key>:<q>:ready` ZSET (by `-priority`) + an atomic
    Lua `promote_and_pop` script. Guarantees no double-dispatch under
    concurrent workers; transparent reload on Redis `NOSCRIPT`.
  - **taskiq**: broker is now auto-selected from `broker_url` scheme —
    `redis://` / `rediss://` / `unix://` → `taskiq_redis.ListQueueBroker`;
    `amqp://` / `amqps://` → `taskiq_aio_pika.AioPikaBroker` (declared with
    `max_priority=9` so RabbitMQ honours per-message priority natively).
    Priority on the Redis broker is routed via `:p<N>` queue suffix
    (operators run `taskiq worker arvel:p9 arvel:p8 ... arvel:p0`).
- New `[queue-amqp]` extra: `arvel[queue-amqp]` installs `taskiq-aio-pika`.
  `arvel[all]` pulls all queue extras.
- New session fixture `rabbitmq_endpoint` and image pin
  `IMAGE_RABBITMQ = "rabbitmq:4.3.0-management-alpine"` for integration tests.
- `docs/adr/ADR-066-job-delay-priority-first-class.md` and
  `docs/adr/ADR-067-taskiq-broker-by-url-scheme.md` documenting the design.

### Changed

- **BREAKING: `arvel[queue]` is now taskiq-only.** Previously the extra pulled
  `taskiq-redis` transitively; now you opt in explicitly:
  - `pip install arvel[queue,queue-redis]` for the Redis Taskiq broker.
  - `pip install arvel[queue,queue-amqp]` for the AMQP (RabbitMQ) broker.
- **BREAKING: `TaskiqQueueConfig.result_backend_url` removed.** The field
  served no purpose (results are not consumed) and is now rejected via
  `extra="forbid"`. Set `QUEUE_TASKIQ_BROKER_URL` only.
- **BREAKING: `DatabaseConnection.push_delayed()` removed.** Set
  `Job.delay` (or pass `Bus.dispatch(..., delay=...)`) instead.
- `Worker` retry path now resets `envelope.delay = 0` so a retried job is a
  continuation, not a re-schedule (the original delay is consumed once on
  first dispatch).
- **Scheduler (WI-019)**: `SchedulerKernel.__init__` now accepts a new
  keyword-only `hooks: SchedulerHooks` parameter. The default (no hooks)
  preserves existing behavior for `Schedule.call(...)`-only apps. Tests that
  previously expected `kind:job` / `kind:command` skip reasons will now see
  `no_dispatch_job_callback` / `no_run_command_callback`.
- **`SchedulerKernel.hooks` is now a public attribute** (WI-020). Promoted
  from `_hooks` to match the project's no-backward-compatibility stance and
  the WI-019 promotion of `_RedisQueueConn`/`_JobRow`. Tests and operator
  scripts inspecting the wired hooks (e.g. to confirm `run_command` is
  set) no longer need to reach into a leading-underscore name.
- **`ServiceProvider.commands()` return type widened** to
  `list[type[Command] | Command]` (WI-020, FR-020-05). Formalizes the
  shape that already exists in the codebase: most providers return stateless
  `Command` types (instantiated by `ConsoleServiceProvider.boot()`), while
  `QueueServiceProvider` returns pre-built instances carrying DI. Existing
  provider subclasses keep working — the contract just got honest.
- **`ReverbStartCommand` is now a `Command` subclass** (WI-020, DEF-020-02).
  Previously duck-typed with `@staticmethod register`; this prevented it
  from satisfying the widened `commands()` contract. No CLI behavior
  change.
- **`SchedulerServiceProvider.boot()` no longer crashes when `base_path`
  is unset** (WI-020, DEF-020-01). The previous code passed
  `getattr(self.app, "base_path", ".")` directly to `Path()`, which fed
  it the bound method instead of the resolved path. Now calls
  `self.app.base_path()` and falls back to `Path()` on
  `EnvironmentNotSetError` / `AttributeError`.
- **`arvel.console.entrypoint.get_commands()`** is now public (was
  `_get_commands`). External tools embedding the CLI can call it; nothing
  changes for normal `arvel --help` users.

### Internal (WI-019)

- Replaced 13 instances of Python-2-style `except A, B:` (parsed by Python 3
  as catching `B` bound to `A`!) with the correct `except (A, B):` tuple
  syntax across `auth/guards/{jwt,token}.py`, `database/migrations.py`,
  `http/middleware/database_transaction.py`, `mail/mailer.py`,
  `reverb/{server,redis_bus}.py`, `session/stores/cookie_.py`,
  `storage/url_signer.py`, `testing/case.py`, `scheduling/kernel.py`, and
  `queue/drivers/{database,redis_,taskiq_}.py`. No behavior change — both
  forms parse to the same AST under Python 3.14 — but the new form is what
  readers expect and unambiguously catches both exception types.

- **S3-compatible storage providers** — the `s3` driver now works with MinIO,
  Cloudflare R2, Hetzner Object Storage, Backblaze B2, DigitalOcean Spaces,
  Wasabi, and any other provider that speaks the S3 wire protocol.
  - `S3Config.public_url` — base URL for `Storage.url(...)` output, lets you
    return a CDN / custom-domain URL while the driver writes via the API
    endpoint (e.g. R2 with a Cloudflare-served custom domain).
  - `S3Config.addressing_style` — `path` (MinIO and most self-hosted setups),
    `virtual` (AWS, R2, Hetzner), or `auto`.
  - `S3Config.signature_version` — defaults to `s3v4`; exposed for the rare
    legacy provider that still needs `s3`.
  - New worked configuration examples in `docs/site/docs/filesystem.md`
    covering MinIO, Cloudflare R2, Hetzner, and a generic rubric.
  - New unit tests in `packages/arvel/tests/storage/test_s3_url.py`
    locking in the `public_url` → `endpoint` → AWS URL priority.

### Changed

- `S3Driver.__init__` is now config-driven — it takes a single `config: S3Config`
  positional argument (plus optional `prefix=` and test-only `**kwargs`).
  The previous per-field params (`bucket=`, `region=`, `endpoint_url=`) were
  silently bypassed when constructed through the framework's
  `StorageManager`, so removing them collapses two construction paths into one.
- `packages/arvel/pyproject.toml` — the `[s3]` extra now pulls `boto3>=1.40.61`
  in addition to `aioboto3>=15.5.0`. The synchronous boto3 client is used by
  `S3Driver.temporary_url` (pre-signing is a local crypto op with no I/O, so
  spinning up an `aioboto3` context for it would be wasteful).

### Fixed

- `S3Config.key` and `S3Config.secret` (`STORAGE_S3_KEY` /
  `STORAGE_S3_SECRET` env vars) now actually reach the boto3 client.
  Previously `StorageManager._create("s3")` only threaded `bucket`, `region`,
  and `endpoint` through, so credentials configured via the typed settings
  were silently dropped — boto3 fell back to `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` env vars or instance profile. This was an awkward
  story for non-AWS providers where users typically don't have ambient AWS
  credentials.
- `S3Driver.url(...)` previously hardcoded the
  `https://<bucket>.s3.<region>.amazonaws.com/<key>` pattern regardless of
  configured endpoint. It now honors `public_url` (CDN / custom domain) and
  `endpoint` (path-style off the API endpoint) before falling back to the
  AWS pattern.
- `S3Driver.temporary_url(...)` previously raised `NotImplementedError`. It
  now returns a working SigV4 pre-signed GET URL across AWS S3, MinIO, R2,
  Hetzner, and other S3-compatible providers.

---

## [0.3.0] — 2026-05-19

Pre-alpha hardening sprint. Core subsystems are complete and working; public
API may change before `1.0`.

### Added

- `arvel[all]` extra — single one-shot install of every optional dependency
  (`pip install 'arvel[all]'`).
- `make dev` now runs `uv sync --all-packages --all-extras` for first-class
  contributor onboarding.
- `benchmarks/scripts/calibrate_bench_reverb.py` — re-runnable calibration
  helper for the broadcasting perf budget. Produces 1.5×-p99 recommended CI
  gate values.
- `bench_resident_memory_tracemalloc()` in `benchmarks/bench_reverb.py` —
  byte-granular Python-heap measurement (was: page-granular `ru_maxrss`).
- New CI jobs: `bench-tracemalloc` (heap-byte perf gate), `sast` (bandit),
  `sca` (pip-audit).
- `.github/workflows/release.yml` — tag-triggered release workflow stub.
  Dry-runs distributions via `twine check` and fails closed (no upload).
- `docs/security/review-*.md` — per-area OWASP Top 10 (2025) security
  reviews (http-auth, broadcasting, query-builder, cache, storage).
- `docs/threat-model.md` — STRIDE matrix covering the framework surface.
- `docs/adr/ADR-065-bench-reverb-hard-gate.md` — calibration methodology
  for the broadcasting perf budget.

### Changed

- `.github/workflows/ci.yml` — `bench-reverb` is now a **hard gate**;
  `continue-on-error: true` removed per ADR-065.
- `packages/arvel/src/arvel/config/registry.py` — added `unregister(cls)`
  test helper to support per-test cleanup of the global config registry.

### Fixed

- **FB-014-001** — Broadcasting perf budget is now CI-enforced.
- **FB-014-002** — Memory budget is now byte-granular via `tracemalloc`.
- **FB-016-001** — `tests/qa_post/test_edge_cases.py::test_config_provider_re_raises_unwrapped_config_error`
  now restores the registry in a `finally` block; downstream tests no longer
  pollute on global state. The defensive skip in
  `test_setup_creates_app_and_client` has been removed.
- All 8 previously-failing JWT tests now SKIP cleanly when `pyjwt` is not
  installed (via `pytest.importorskip("jwt")` at module scope). They run
  fully when the `arvel[jwt]` extra is installed.
- All inline `# nosec` annotations now include both a CWE code AND a
  one-line rationale (FR-017-015). CI enforces this via
  `tests/hardening/test_nosec_annotations.py`.
- `tests/testing/fakes/cache.py` — dropped the `/tmp` default that bandit
  flagged as B108; the ARRAY driver doesn't use `file_path` anyway.

### Security

- Full OWASP Top 10 (2025) review of the public surface — 0 MEDIUM+ bandit
  findings, 0 known CVEs in resolved deps.
- See `docs/security/review-*.md` for per-area findings.
- Release workflow fails closed (SEC-017-004): never publishes without
  explicit Trusted Publisher configuration on PyPI.

### Breaking changes

None. `0.3.0` is purely additive vs `0.1.0`; the only "removal" is a defensive
test skip that was masking a fixed bug.

### Upgrade notes

- From 0.1.0: drop-in. No code changes required. Recommended:
  `pip install 'arvel[all]'` to align with the new canonical install.

---

## [0.1.0] — 2026-05-19

First public alpha release. Arvel becomes installable from PyPI as
`pip install arvel==0.1.0` (once published — see `docs/ops/release-checklist.md`).

### Added (cumulative since project start)

This is the consolidated 0.1.0 set. Refer to per-WI deployment checklists
under `docs/ops/` for sprint-level detail.

#### Foundations (WI-001..006)
- ApplicationBuilder, two-pass bootstrap, container with autowiring
- ConfigServiceProvider with strict-typed `pydantic-settings` models
- Console (Typer) entrypoint and command discovery
- HTTP layer (FastAPI under the hood) — controllers, middleware, exception handlers
- Eloquent-style ORM (SQLAlchemy) — models, relations, query builder
- Application shape: bootstrap, routes, providers, console kernel discovery
- Console+ORM tail: `make:model`, `make:migration`, `db:fresh`, `db:seed`
- Cache, Sessions, Storage with multiple drivers (Redis, File, S3, GCS, Azure)

#### Auth + Queues + Messaging (WI-007..009)
- Auth: bcrypt + argon2 hash facade, JWT guard, session guard, form-requests
- Queues: TaskIQ adapter, in-DB driver, retry/back-off, failed-jobs table
- Mail (aiosmtplib), Notification framework, multi-channel (mail + db + slack stubs)

#### Database completion + Realtime (WI-010..014)
- Polymorphic relations, BelongsToMany, soft deletes, observers, scopes, encrypted columns
- Queue worker retry+DLQ + admin commands
- Reverb-style WebSocket broadcasting (Pusher-protocol-compatible)
- Realtime hardening: perf benchmarks

#### Scheduler + Logging + i18n (WI-015)
- `arvel.scheduling` — Laravel-style cron DSL + `SchedulerKernel`, `arvel schedule:work`
- `arvel.logging_` — `Log` facade, channel-based drivers (single/daily/stderr/syslog/slack/stack/null)
- `arvel.i18n` — `__()`/`__choice()` helpers, Python-file translation backend
- 3 new ServiceProviders: `SchedulerServiceProvider`, `LogServiceProvider`, `LangServiceProvider`

#### Test utilities (WI-016)
- `arvel.testing.ArvelTestCase` — pytest-friendly base class with auto app boot/teardown
- `arvel.testing.TestResponse` — fluent HTTP assertions (≥20 helpers)
- `arvel.testing.fixtures` — `arvel_app`, `arvel_client`, `arvel_database` pytest fixtures
- Facade `.fake()` helpers — `Cache.fake()`, `Event.fake()`, `Storage.fake()` (Mail.fake already shipped)

### Notes

- Python 3.14+ required (we use `Self`, `TaskGroup`, modern `Literal` patterns)
- Strict type-checking: `mypy --strict` passes on all 281 source files
- ~1500 tests, all green

### Known gaps (deferred to 1.0 — see WI-017)

- Queue/Bus/Notification fakes (planned for 0.1.1)
- Model factories (ORM Factory pattern)
- Performance bench gate in CI
- PyPI publishing automation
- Comprehensive security audit

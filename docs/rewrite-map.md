<!-- Working map for the docs rewrite. The reference framework is never named in-repo. -->

# Reference → Arvel documentation section map

The master index driving the docs rewrite. Every the reference framework doc section is mapped to the Arvel
page(s) that should cover it, with a coverage verdict. Rewrite order follows this file top to
bottom. **Hygiene:** this ops-repo file names the reference framework; the in-repo `docs/` and `docs/GAPS.md`
never do (they say "the reference framework").

Legend:
- **✅ covered** — Arvel page exists and covers the topic; rewrite = restyle/verify only.
- **◐ partial** — exists but missing sub-topics the reference covers; rewrite = restyle + fill.
- **➕ new** — no Arvel page; the feature exists in code but is undocumented or scattered.
- **⚠ gap** — the feature itself is missing/incomplete in Arvel → record in `docs/GAPS.md`.
- **✚ arvel-extra** — Arvel page with no the reference framework equivalent; keep, style to match.
- **∅ n/a** — reference-only (a first-party product/tool) with no Arvel analogue; skip.

---

## Prologue
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Release Notes | CHANGELOG.md (exists) | ✅ leave |
| Upgrade Guide | — | ∅ pre-1.0, no upgrade path yet |
| Contribution Guide | — | ∅ (repo has its own) |

## Getting Started
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Installation | getting-started.md | ✅ DONE (PR #281) |
| Configuration | configuration.md | ◐ add: debug mode, maintenance mode (`arvel down/up` exists), config precedence; no config:cache (defer) |
| Directory Structure | **structure.md** | ➕ new — verify against `_skeleton/app` (app/ bootstrap/ config/ database/ routes/ resources/ tests/) |
| Frontend | views.md (+ frontend split) | ◐ Vite manifest + Inertia exist; split a Frontend section |
| Starter Kits | — | ⚠ G-02 — profiles + `--auth` only; no complete-app kit |
| Deployment | **deployment.md** | ➕ new — verify serve/ASGI story (granian/uvicorn), env, migrate |

## Architecture Concepts
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Request Lifecycle | **lifecycle.md** (or architecture.md) | ◐ material in about/architecture; needs a reference-shaped lifecycle page |
| Service Container | container.md | ✅ verify (bindings, scoped, contextual, `make`, autowiring) |
| Service Providers | providers.md | ✅ verify (register/boot, deferred) |
| Facades | facades.md | ✅ verify (how they resolve, real-time facades?) |

## The Basics
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Routing | routing.md | ✅ verify (params, groups, model binding, rate limit, signed) |
| Middleware | middleware.md | ✅ verify (groups, aliases, priority, params) |
| CSRF Protection | **csrf** (own page or middleware split) | ◐ ValidateCsrfToken exists in middleware.md — reference gives it its own page |
| Controllers | routing.md (Controller) | ◐ Controller class + resource routes exist; reference has own page |
| Requests | **requests.md** (split from routing) | ◐ Request/input bag well-covered in getting-started+routing; reference dedicates a page |
| Responses | **responses.md** (new/split) | ◐ Response, redirects, JSON, files — scattered; consolidate |
| Views | views.md | ✅ verify (Jinja, share, composers?) |
| Templates | views.md (Jinja section) | ◐ Jinja is the analogue; document directives/inheritance/components |
| Asset Bundling (Vite) | views.md frontend / **frontend.md** | ◐ Vite manifest reader exists |
| URL Generation | routing.md / **urls.md** | ◐ `route()`/`url()`/signed URLs exist; reference dedicates a page |
| Session | **session.md** (split from middleware) | ◐ StartSession/flash/driver in middleware.md; reference dedicates a page |
| Validation | validation.md | ✅ verify (rules, FormRequest, custom, errors) |
| Error Handling | errors.md | ✅ verify (render, report, HTTP exceptions) |
| Logging | logging.md | ✅ verify (channels, context, structlog) |

## Digging Deeper
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Console | console.md | ✅ verify (commands, args/opts, generators, scheduler) |
| Broadcasting | broadcasting.md | ✅ verify |
| Cache | cache.md | ✅ verify (stores, tags, locks, remember) |
| Collections | helpers.md (Collection split) | ◐ Collection exists; reference dedicates a page |
| Concurrency | concurrency.md | ✅ verify |
| Context | context.md | ✅ verify |
| Contracts | **contracts.md** | ➕ new small — `arvel.contracts` protocols |
| Events | events.md | ✅ verify (dispatch, listeners, subscribers, queued) |
| File Storage | storage.md | ✅ verify (disks, s3/gcs/azure, temporary_url) |
| Helpers | helpers.md | ✅ verify (arr/str/etc) |
| HTTP Client | http-client.md | ✅ verify (retry, pool, fake) |
| Localization | localization.md | ✅ verify |
| Mail | mail.md | ✅ verify (mailables, markdown, queue) |
| Notifications | notifications.md | ✅ verify (channels, on-demand, db) |
| Package Development | packaging.md | ✅ verify |
| Processes | processes.md | ✅ verify |
| Queues | queues.md | ✅ verify (jobs, batches, retries, failed) |
| Rate Limiting | middleware.md (RateLimiter split) | ◐ RateLimiter exists; reference dedicates a page |
| Strings | helpers.md (Str/Stringable split) | ◐ Stringable exists; reference dedicates a page |
| Task Scheduling | console.md (scheduler split) | ◐ scheduler exists; reference dedicates a page |
| — | dates.md | ✚ arvel-extra (Date/Carbon-analogue) — keep |
| — | money.md | ✚ arvel-extra — keep |
| — | pipeline.md | ✚ arvel-extra (the reference framework has Pipeline in helpers) |
| — | features.md | ✚ arvel-extra (feature flags — the reference framework = Pennant, a package) |
| — | media.md | ✚ arvel-extra (the reference framework = Spatie package) |
| — | search.md | ✚ arvel-extra (the reference framework = Scout, a package) |
| — | telemetry.md | ✚ arvel-extra (the reference framework = Telescope/Pulse, packages) |
| — | activitylog.md | ✚ arvel-extra (the reference framework = Spatie package) |
| — | openapi.md | ✚ arvel-extra |

## Security
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Authentication | auth/authentication.md | ✅ verify (guards, providers, tokens) |
| Authorization | auth/authorization.md | ✅ verify (gates, policies, before) |
| Email Verification | auth/routes-and-flows.md | ◐ verify the flow exists (F-25 test proves email-verify routes exist) |
| Encryption | encryption.md | ✅ verify |
| Hashing | hashing.md | ✅ verify |
| Password Reset | auth pages | ⚠ VERIFY it exists — reference core feature; grep for reset flow, gap if absent |

## Database
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Getting Started | database/index.md | ✅ verify (connections, raw, transactions link) |
| Query Builder | database/queries.md | ✅ DONE-ish (ORM wave filled it) — restyle |
| Pagination | pagination.md | ✅ verify |
| Migrations | database/migrations.md | ✅ recently gap-filled — restyle |
| Seeding | database/index or console | ◐ Seeder exists (DR-0034); needs a Seeding section |
| Redis | — | ∅ (cache/queue drivers cover it; no dedicated Redis page) |
| MongoDB | — | ∅ n/a |

## ORM
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Getting Started | database/index.md | ✅ verify (model basics) |
| Relationships | database/relationships.md | ✅ recently gap-filled (morph_map) — restyle |
| Collections | database/relationships.md#model-collection | ◐ ModelCollection — could be its own page |
| Mutators & Casts | database/attributes.md + casts.md | ✅ DONE (attributes.md new) — restyle casts |
| API Resources | database/resources.md | ✅ verify (JsonResource, JsonApiResource) |
| Serialization | database/attributes.md / casts.md | ◐ to_dict/to_json/hidden/appends — covered in attributes; cross-link |
| Factories | database/factories.md | ✅ recently touched — restyle |

## Testing
| Reference | Arvel target | Verdict |
|---------|-------------|---------|
| Getting Started | testing.md | ✅ verify |
| HTTP Tests | testing.md | ✅ verify (client, assertions) |
| Console Tests | testing.md | ◐ verify Cli.call test seam |
| Database | testing.md | ✅ recently touched (begin_test_transaction) |
| Mocking | testing.md (fakes) | ✅ verify (fake(), spies) |

## Reference first-party products — n/a
Products with no Arvel core analogue are skipped; the closest Arvel analogues are the "extra" pages tagged above.


---

## Rewrite batches (execution order, one branch)
1. **Getting Started group** — configuration (fill), structure (new), frontend (split), deployment (new). [G-02 done]
2. **Architecture** — lifecycle (new), container/providers/facades (verify+restyle).
3. **The Basics A** — routing, middleware, csrf (split), controllers/requests/responses (split).
4. **The Basics B** — views/templates/frontend, urls (split), session (split), validation, errors, logging.
5. **Digging Deeper A** — console+scheduling, cache, events, queues, storage, http-client.
6. **Digging Deeper B** — collections/strings (split), helpers, localization, mail, notifications, broadcasting, processes, concurrency, context, contracts (new), rate-limiting (split), packaging.
7. **Security** — auth pages, encryption, hashing, email-verify, password-reset (VERIFY/gap).
8. **Database + ORM** — index, queries, migrations, seeding, relationships, resources, factories, casts, pagination, transactions.
9. **Testing** — the testing page (possibly split HTTP/Console/DB/Mocking).
10. **Arvel-extras pass** — dates, money, pipeline, features, media, search, telemetry, activitylog, openapi: style to match, keep.

Each batch: verify claims against code (run behavioral examples), record gaps in docs/GAPS.md +
ops ledger, `zensical build`, commit. Independent review at batch boundaries; STOP at merge gate.

---

# Target nav structure (mirrors the reference framework's grouping/order)

Proposed `zensical.toml` nav, reorganized from the current tree so the top-level groups and their
ordering match the reference framework: **Getting Started → Architecture Concepts → The Basics → Digging Deeper →
Security → Database → ORM → Testing**. `(NEW)` = page to create; `(split)` = carve out
of an existing page; everything else is an existing page re-homed. Arvel-only pages are placed in
the closest the reference framework group and tagged `[extra]`.

```
Home                              index.md

Getting Started
  Installation                    getting-started.md
  Configuration                   configuration.md
  Directory Structure             structure.md            (NEW)
  Frontend                        frontend.md             (split from views.md)
  Deployment                      deployment.md           (NEW)

Architecture Concepts
  Request Lifecycle               lifecycle.md            (NEW; from about/architecture)
  Service Container               container.md
  Service Providers               providers.md
  Facades                         facades.md
  Packaging & Extras              packaging.md            [extra: the reference framework "Package Development"]

The Basics
  Routing                         routing.md
  Middleware                      middleware.md
  CSRF Protection                 csrf.md                 (split from middleware.md)
  Controllers                     controllers.md          (split from routing.md)
  Requests                        requests.md             (split; input bag lives in routing/getting-started)
  Responses                       responses.md            (NEW/consolidate)
  Views                           views.md
  Templates                       templates.md            (split from views.md — Jinja is the template-engine analogue)
  URL Generation                  urls.md                 (split from routing.md)
  Session                         session.md              (split from middleware.md)
  Validation                      validation.md
  Error Handling                  errors.md
  Logging                         logging.md

Digging Deeper
  Console                         console.md              [the reference framework "Console"]
  Task Scheduling                 scheduling.md           (split from console.md)
  Broadcasting                    broadcasting.md
  Cache                           cache.md
  Collections                     collections.md          (split from helpers.md)
  Concurrency                     concurrency.md
  Context                         context.md
  Contracts                       contracts.md            (NEW small)
  Events                          events.md
  File Storage                    storage.md
  Helpers                         helpers.md
  HTTP Client                     http-client.md
  Localization                    localization.md
  Mail                            mail.md
  Notifications                   notifications.md
  Processes                       processes.md
  Queues                          queues.md
  Rate Limiting                   rate-limiting.md        (split from middleware.md)
  Strings                         strings.md              (split from helpers.md — Stringable/Str)
  — Arvel extras —
  Dates & Time                    dates.md                [extra]
  Money                           money.md                [extra]
  Pipeline                        pipeline.md             [extra]
  Feature Flags                   features.md             [extra: the reference framework Pennant]
  Media Library                   media.md                [extra: the reference framework Spatie]
  Search                          search.md               [extra: the reference framework Scout]
  Telemetry                       telemetry.md            [extra: the reference framework Telescope/Pulse]
  Activity Log                    activitylog.md          [extra: the reference framework Spatie]
  OpenAPI & API Docs              openapi.md              [extra]

Security
  Authentication                  auth/authentication.md
  Authorization                   auth/authorization.md
  Email Verification              auth/email-verification.md  (split from routes-and-flows.md)
  Encryption                      encryption.md
  Hashing                         hashing.md
  Password Reset                  auth/password-reset.md      (VERIFY exists → doc or GAP)
  — Arvel auth extras —
  Guards & Drivers                auth/guards.md          [extra]
  API Tokens                      auth/api-tokens.md      [extra: the reference framework Sanctum]
  Two-Factor Auth                 auth/two-factor.md      [extra: the reference framework Fortify]
  Single Sign-On (OIDC)           auth/sso-oidc.md        [extra]
  OAuth2 Social Login             auth/oauth.md           [extra: the reference framework Socialite]
  IdP Groups → Roles              auth/idp-roles.md       [extra]
  Identities & Account Linking    auth/identities.md      [extra]
  Routes & Flows                  auth/routes-and-flows.md [extra]
  Providers & Middleware          auth/providers-and-middleware.md [extra]
  Auth Configuration              auth/configuration.md   [extra]

Database
  Getting Started                 database/index.md
  Query Builder                   database/queries.md
  Pagination                      pagination.md
  Migrations                      database/migrations.md
  Seeding                         database/seeding.md     (split — Seeder/DR-0034)
  — Arvel db extras —
  Transactions & Streaming        database/transactions.md
  CTEs & Recursive Queries        database/ctes.md        [extra]
  SQL Views & Functions           database/sql-views.md   [extra]
  JSON, Full-Text & Vectors       database/json-search.md [extra]

ORM
  Getting Started                 database/index.md (models section) or models.md (split)
  Relationships                   database/relationships.md
  Collections                     database/collections.md  (split from relationships #model-collection)
  Mutators & Casts                database/attributes.md + database/casts.md
  API Resources                   database/resources.md
  Serialization                   (attributes.md/casts.md cross-link)
  Factories                       database/factories.md

Testing
  Getting Started                 testing.md
  HTTP Tests                      testing.md (or split)
  Console Tests                   testing.md (or split)
  Database                        testing.md
  Mocking                         testing.md (fakes)

About arvel                       about.md
```

## Structural deltas from the current nav (what moves)
- **Configuration** moves The Basics → Getting Started (the reference framework's placement).
- **Database** splits into **Database** (query builder, migrations, seeding, pagination) + **the ORM
  ORM** (models, relationships, casts, resources, factories) — currently one flat group.
- **The Basics** gains CSRF, Controllers, Requests, Responses, Templates, URLs, Session, Logging
  (mostly splits from routing/middleware/views).
- **Digging Deeper** gains Task Scheduling, Collections, Strings, Rate Limiting, Contracts (splits);
  Localization/Console stay; Logging leaves (→ The Basics).
- **Security** foregrounds the 6 the reference framework-core topics (authn, authz, email-verify, encryption,
  hashing, password-reset); arvel's richer auth stack (SSO/OIDC/OAuth/2FA/tokens/…) sits below as
  extras.
- **Arvel-extras** (dates, money, pipeline, features, media, search, telemetry, activitylog,
  openapi) are retained, each parked in its nearest the reference framework group and tagged.

## New pages this structure requires
structure.md, deployment.md, lifecycle.md, frontend.md, csrf.md, controllers.md, requests.md,
responses.md, templates.md, urls.md, session.md, scheduling.md, collections.md, contracts.md,
rate-limiting.md, strings.md, auth/email-verification.md, auth/password-reset.md,
database/seeding.md, database/collections.md — created only where the feature EXISTS (verify
first); otherwise the topic becomes a GAP entry, not a page.

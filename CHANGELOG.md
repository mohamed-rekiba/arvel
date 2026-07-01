# Changelog

## [0.48.0](https://github.com/mohamed-rekiba/arvel/compare/v0.47.0...v0.48.0) (2026-07-01)


### Features

* **auth:** HasRoles.remove_role — revoke a role (Spatie removeRole parity) ([733510c](https://github.com/mohamed-rekiba/arvel/commit/733510ca99490445eef8f56a94d6e57124c8ecc6))
* **auth:** Role.permissions() — a role's granted permissions (Spatie parity) ([95cfada](https://github.com/mohamed-rekiba/arvel/commit/95cfada89cca35f1e463fb9ea454da8457ed5135))
* **boundaries:** enforce the module DAG via import-linter layers (empty allowlist) ([162f360](https://github.com/mohamed-rekiba/arvel/commit/162f3603deadd93f8d55479336935a28ca1ae3b8))
* **client:** Client.timeout() chainable (parity with base_url/with_headers) ([709f470](https://github.com/mohamed-rekiba/arvel/commit/709f470a12a417c8c0d875413cf2c7cada077fff))
* **console:** add missing Laravel commands (migrate:fresh/refresh, db:wipe, cache:clear, key:generate, storage:link, make:enum/exception/test) ([3014f09](https://github.com/mohamed-rekiba/arvel/commit/3014f09a518195ed575cbbba8a13ab4d3e5d6059))
* **console:** plain ASCII banner on bare `arvel`, no color ([755fcba](https://github.com/mohamed-rekiba/arvel/commit/755fcba2f0de8a2e78061dfc0f1ed5a1957e496b))
* **extras:** add an 'oidc' optional-dependency extra (pyjwt[crypto]) ([14396bb](https://github.com/mohamed-rekiba/arvel/commit/14396bbc98dd0f1be4fe58c276291d36c44faf3a))
* **http:** typed query parameters — injected + documented in OpenAPI ([34b82d2](https://github.com/mohamed-rekiba/arvel/commit/34b82d2a3678e9880abf5f9e16af42c4c00bc5e2))
* **i18n:** translatable model attributes (HasTranslations + Translatable cast) ([777276d](https://github.com/mohamed-rekiba/arvel/commit/777276deb97d8da269abebf59c8d34ff81ac7be2))
* **i18n:** translatable model attributes (HasTranslations + Translatable cast) ([392ab7c](https://github.com/mohamed-rekiba/arvel/commit/392ab7ca716d824137cd2b1aa7d550ab4160dcd4))
* **mail:** app-wide default sender (config mail.from) — Laravel parity ([e96587d](https://github.com/mohamed-rekiba/arvel/commit/e96587dab88673230fff8ca6291332a94747b9f2))
* **openapi:** OpenID Connect security scheme (.secure("oidc")) ([30bbd72](https://github.com/mohamed-rekiba/arvel/commit/30bbd72d716ca566c80982ade72f8263b156ac6e))
* **orm,http:** Laravel-parity relation serialization + conditional clauses ([7ae5798](https://github.com/mohamed-rekiba/arvel/commit/7ae57988fbc4f48bfd12cf4322ba1537f80f02fc))
* **orm,http:** ModelNotFound renders as 404 + export migration Schema type ([29a479a](https://github.com/mohamed-rekiba/arvel/commit/29a479a2b32916d70a824ba590d190d9e7229677))
* **orm:** typed classmethod query entry-points (Model.where/with_/order_by/...) ([ac735d4](https://github.com/mohamed-rekiba/arvel/commit/ac735d47fcbf4da196fd021253b708686d82e850))
* **orm:** where_in accepts a subquery (Laravel whereIn(col, $subquery)) ([79a1276](https://github.com/mohamed-rekiba/arvel/commit/79a12765b94dbe2ea83056f6dc5b1d4abb6c20ae))
* **orm:** where_json_like — LIKE against a value inside a JSON column ([bdd5d06](https://github.com/mohamed-rekiba/arvel/commit/bdd5d0678fcc048d439eeccc046914b57fdcdb87))
* **orm:** where_raw + where_exists (Laravel whereRaw / whereExists) ([013e73e](https://github.com/mohamed-rekiba/arvel/commit/013e73e5a7a6a135b207518df3df453ded311089))
* **routing:** per-route response status override (Route.post(...).status(200)) ([9f0e903](https://github.com/mohamed-rekiba/arvel/commit/9f0e90346f001ece44dda6244d8d5b813a5c1a78))
* **schema:** t.btree_index — composite + expression indexes (jsonb per-locale lookups) ([3e541e4](https://github.com/mohamed-rekiba/arvel/commit/3e541e4e1e9c8d6aba8b0a7c3cdb7a898bdf857a))
* **schema:** warn + degrade Postgres-only DDL on other dialects ([4161e18](https://github.com/mohamed-rekiba/arvel/commit/4161e18c1505f8b8e2c33c6874d54b81f171e737))
* **search:** Searchable.make_all_searchable + remove_all_from_search (Scout parity) ([eff2dd6](https://github.com/mohamed-rekiba/arvel/commit/eff2dd6be92fba37dd360f63022283ebb616f29e))
* **testing:** reset_rate_limiter/reset_sessions for test isolation ([5503547](https://github.com/mohamed-rekiba/arvel/commit/55035475ce11182e12427622160d67db5aa963a7))


### Bug Fixes

* **boundaries:** maintenance resolves cache itself (http-&gt;cache legal) ([d4a4326](https://github.com/mohamed-rekiba/arvel/commit/d4a4326dfce8cd3c82ca306f9429867b904ba615))
* **console:** --help shows the Laravel colon command names (not hyphenated) ([da14e1b](https://github.com/mohamed-rekiba/arvel/commit/da14e1b13de7de4af24bd0621ee78cac225d4107))
* **http:** builder global middleware actually runs on the served app ([551e08e](https://github.com/mohamed-rekiba/arvel/commit/551e08e3f9efa86de02d8e0f678980b7e4c0f55b))
* **i18n:** set_translation stores a dict, not a double-encoded string (review finding) ([d152d9c](https://github.com/mohamed-rekiba/arvel/commit/d152d9c2af7ba1aefca54c58db7aab0db887ee4a))
* **i18n:** Translatable.set returns a dict (JSON column serializes once) ([31b082c](https://github.com/mohamed-rekiba/arvel/commit/31b082c4e253b6cd16b601d5e5faec370739a09c))
* **migrate:** drop_all drops views/materialized views first (Postgres) ([d65c3cf](https://github.com/mohamed-rekiba/arvel/commit/d65c3cf569ae9083558cc8076228c502d40026b6))
* **migrate:** idempotent migrations + concise CLI errors (no traceback wall) ([80035f8](https://github.com/mohamed-rekiba/arvel/commit/80035f8a05b422d73b8bcdda2101c226c51d5e5a))
* **openapi:** handler docstring becomes the operation description ([8770daf](https://github.com/mohamed-rekiba/arvel/commit/8770daf1a3342197f07a8f522ca974cc36f08e83))
* **orm:** timestamps on by default (Laravel parity) + datetime-safe json cast ([a92c7d8](https://github.com/mohamed-rekiba/arvel/commit/a92c7d8f5f128e3d0b01234bc40ed171d35738cd))
* **orm:** update query syntax for model retrieval to match Laravel style ([aa4429c](https://github.com/mohamed-rekiba/arvel/commit/aa4429c9a097a24c4392c3ab5ebe88d16d680b64))
* **types:** annotate _build_served_asgi with concrete Application for serve_lifespan ([9c81d64](https://github.com/mohamed-rekiba/arvel/commit/9c81d64851f48fedead90f56e895b810d600c9f8))
* **types:** explicit re-export of current_user from http.request ([ab6e0cf](https://github.com/mohamed-rekiba/arvel/commit/ab6e0cf431025c5a76eb79aede3e4093cacfe01a))


### Refactors

* **boundaries:** break auth&lt;-&gt;http cycle (unify current_user in support) ([77ab091](https://github.com/mohamed-rekiba/arvel/commit/77ab0914f369bf3fc4d7a6a6dc6f439479c8bd9a))
* **boundaries:** break cache&lt;-&gt;support cycle ([f4ea395](https://github.com/mohamed-rekiba/arvel/commit/f4ea395113e14dbbb04d4e20c89c7f4c26606349))
* **boundaries:** break http&lt;-&gt;pagination and pagination&lt;-&gt;views cycles ([e866405](https://github.com/mohamed-rekiba/arvel/commit/e8664051a41ee021f65dec438f8be649e22ee93f))
* **boundaries:** break http&lt;-&gt;telemetry cycle (prometheus split) ([eb43aa1](https://github.com/mohamed-rekiba/arvel/commit/eb43aa174a3b7dd94ce032ce61b0eda02b0a470e))
* **boundaries:** break kernel-&gt;telemetry and kernel-&gt;http cycles ([d1a2a9b](https://github.com/mohamed-rekiba/arvel/commit/d1a2a9b99998a7ab6f46b0b4f4fd9a60a3fa53ff))
* **boundaries:** drop eager telemetry-&gt;http middleware base ([bfecbc8](https://github.com/mohamed-rekiba/arvel/commit/bfecbc88f48adddd01b6f6b9d3aeddb80e5f337e))


### Documentation

* **console:** list the new commands (migrate:fresh/refresh, db:wipe, cache:clear, key:generate, storage:link, make:enum/exception/test) ([6da52b1](https://github.com/mohamed-rekiba/arvel/commit/6da52b1d74fc25531f9cb52a1e0642d20a5d7f54))
* sync docs with the features added this round ([c4e29da](https://github.com/mohamed-rekiba/arvel/commit/c4e29dae014e452f39bba73928afa3d916c37e63))

## [0.47.0](https://github.com/mohamed-rekiba/arvel/compare/v0.46.2...v0.47.0) (2026-06-29)


### Features

* **console:** make:event, make:listener, make:cast generators ([e26beac](https://github.com/mohamed-rekiba/arvel/commit/e26beacb8bd257b244891c48e70106b15033bf72))
* **database:** model observers + fix queued binary attachments over a real broker ([6ec8e7d](https://github.com/mohamed-rekiba/arvel/commit/6ec8e7d0f99547296a76164c8cc21cc8fbbbc7e1))
* **http:** HTML form method-spoofing (Laravel [@method](https://github.com/method)) ([81b1a1f](https://github.com/mohamed-rekiba/arvel/commit/81b1a1fce9021e09f5e0025715183792be1878f9))
* multipart [@method](https://github.com/method), per-app manager config, richer reference app ([d7e29c4](https://github.com/mohamed-rekiba/arvel/commit/d7e29c4cbf7a8672e2b6d0f26fc27498990f428a))
* **routing:** signed-URL key defaults to app key + ValidateSignature (signed) middleware ([d447141](https://github.com/mohamed-rekiba/arvel/commit/d447141fb810df601e5f72f5466888974c51b989))
* **scaffold:** ship cache/filesystems/mail config files (Laravel parity + discoverability) ([e77f04e](https://github.com/mohamed-rekiba/arvel/commit/e77f04e7cbd8e611f04b8abdd5a3f76b850d464a))
* **views:** auth()/guest() template globals (Laravel @auth/[@guest](https://github.com/guest)) ([0858d2b](https://github.com/mohamed-rekiba/arvel/commit/0858d2bddcda84c86f1d8ec267bcc6b6a697e2ed))


### Bug Fixes

* **mail,notifications:** queued mailables/notifications survive a real broker ([da9c9de](https://github.com/mohamed-rekiba/arvel/commit/da9c9de18b4d0448b5a8463e909d5ba2fa3f29af))


### Refactors

* **queue:** QueueManager is now a Manager subclass ([3a9bb14](https://github.com/mohamed-rekiba/arvel/commit/3a9bb142309447f2c7557092d85cb28722ca3a25))

## [0.46.2](https://github.com/mohamed-rekiba/arvel/compare/v0.46.1...v0.46.2) (2026-06-29)


### Bug Fixes

* **queue,db:** address review nits — TEXT columns, AMQP startup leak, pin collector ([8070167](https://github.com/mohamed-rekiba/arvel/commit/80701670aa56fb1a04791aba92fe01ae6dc7c116))


### Documentation

* testing.md integration tier, migrations.md default string length. ([f898c42](https://github.com/mohamed-rekiba/arvel/commit/f898c42340e6601c0d19c58e4559f11d4189075f))

## [0.46.1](https://github.com/mohamed-rekiba/arvel/compare/v0.46.0...v0.46.1) (2026-06-29)


### Bug Fixes

* **database:** store datetimes as UTC so SQLite round-trips keep the instant (review B1) ([3d52898](https://github.com/mohamed-rekiba/arvel/commit/3d52898bba6dc3f5faf8b05965c8447b20a01208))

## [0.46.0](https://github.com/mohamed-rekiba/arvel/compare/v0.45.0...v0.46.0) (2026-06-29)


### Features

* **database:** store datetimes as real DateTime values, not ISO strings (DR-0023) ([c15c846](https://github.com/mohamed-rekiba/arvel/commit/c15c84682e27bf041f4d744d8d80c5c6f66715e2))

## [0.45.0](https://github.com/mohamed-rekiba/arvel/compare/v0.44.1...v0.45.0) (2026-06-29)


### Features

* **pagination:** Laravel-parity paginators (paginate/simple_paginate, links(), JSON) ([2ff86f2](https://github.com/mohamed-rekiba/arvel/commit/2ff86f24e6a30a3febd24df4db360f7affac4fbb))


### Bug Fixes

* **pagination:** address review nits (per_page&gt;=1 guard, list query params, real e2e date proof) ([ce7df61](https://github.com/mohamed-rekiba/arvel/commit/ce7df6123d3751bdba5407332836540343456924))

## [0.44.1](https://github.com/mohamed-rekiba/arvel/compare/v0.44.0...v0.44.1) (2026-06-29)


### Bug Fixes

* resolve the formating issues ([5c42ee8](https://github.com/mohamed-rekiba/arvel/commit/5c42ee8b79dbc78625868b6d4269e99f6641b63e))

## [0.44.0](https://github.com/mohamed-rekiba/arvel/compare/v0.43.1...v0.44.0) (2026-06-29)


### Features

* **telemetry:** auto-instrument cache + outbound HTTP, and propagate traces to queue jobs ([07a835f](https://github.com/mohamed-rekiba/arvel/commit/07a835f169551af7ba0bb1f3c2c5d549f0d816d4))

## [0.43.1](https://github.com/mohamed-rekiba/arvel/compare/v0.43.0...v0.43.1) (2026-06-29)


### Documentation

* make the docs consistent with the merged observability features ([a20bdcc](https://github.com/mohamed-rekiba/arvel/commit/a20bdcc1f19543d7fc921b1e24895521af8ec6ba))
* **telemetry:** add a hands-on "new to observability" tour with real output ([09c9ad7](https://github.com/mohamed-rekiba/arvel/commit/09c9ad7c97d54672f6315867f886fb3a67dd5861))

## [0.43.0](https://github.com/mohamed-rekiba/arvel/compare/v0.42.0...v0.43.0) (2026-06-29)


### Features

* **telemetry:** auto-instrument database queries with OpenTelemetry CLIENT spans ([41e65d4](https://github.com/mohamed-rekiba/arvel/commit/41e65d496ac5c1a549550fb697e87480c4de9ca3))
* **telemetry:** record HTTP request metrics (count + duration) in the middleware ([c73bdbb](https://github.com/mohamed-rekiba/arvel/commit/c73bdbb26d5e61e7f2396c1de73650bd572d2488))


### Bug Fixes

* format code for better readability in telemetry processing functions ([b8ea2dc](https://github.com/mohamed-rekiba/arvel/commit/b8ea2dc2daea5d731729e2e561da7abc899a31ca))

## [0.42.0](https://github.com/mohamed-rekiba/arvel/compare/v0.41.0...v0.42.0) (2026-06-28)


### Features

* **telemetry:** auto-instrument HTTP requests with OpenTelemetry server spans ([28a8a1a](https://github.com/mohamed-rekiba/arvel/commit/28a8a1ae45505176041ff9623990385ffcae94b7))
* **telemetry:** export metrics and logs alongside traces (full OTLP signal set) ([e7adf38](https://github.com/mohamed-rekiba/arvel/commit/e7adf3853e2c34d9dbe34b7e81915c3e23f8d96c))

## [0.41.0](https://github.com/mohamed-rekiba/arvel/compare/v0.40.0...v0.41.0) (2026-06-28)


### Features

* **telemetry:** OpenTelemetry tracing wired from config, backend-agnostic via OTLP ([538efae](https://github.com/mohamed-rekiba/arvel/commit/538efae1d7021dbe9106c1c43f0d47025411d34c))


### Bug Fixes

* **queue:** reserve delayed jobs atomically so concurrent workers never double-release ([a59b6ac](https://github.com/mohamed-rekiba/arvel/commit/a59b6ac3755fcb7b3da4881b487c984a33be14ee))

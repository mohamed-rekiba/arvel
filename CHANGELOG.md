# Changelog

## [0.66.0](https://github.com/mohamed-rekiba/arvel/compare/v0.65.0...v0.66.0) (2026-07-17)


### Features

* auto-discover listeners from app/listeners/ at boot ([8b7b495](https://github.com/mohamed-rekiba/arvel/commit/8b7b495e337e125d8926d90da8a8f0ad330e0fdb))

## [0.65.0](https://github.com/mohamed-rekiba/arvel/compare/v0.64.0...v0.65.0) (2026-07-15)


### Features

* Round out the package skeleton for publishing ([380a08e](https://github.com/mohamed-rekiba/arvel/commit/380a08e2877c3c41ab40f1e92439994066d76384))

## [0.64.0](https://github.com/mohamed-rekiba/arvel/compare/v0.63.4...v0.64.0) (2026-07-14)


### Features

* **filesystem,cache:** typed driver enums (FilesystemDriver / CacheDriver) ([98b4fee](https://github.com/mohamed-rekiba/arvel/commit/98b4feed34c7101361c9a64f1bb954c586d1c8bd))
* **health:** document /livez in the schema (typed liveness response) ([f836753](https://github.com/mohamed-rekiba/arvel/commit/f8367530a21bfdec17841d1223cac89546f04cd9))
* **mail:** MailDriver.ROUND_ROBIN + docs: LazyCollection ([f9b49aa](https://github.com/mohamed-rekiba/arvel/commit/f9b49aace10f9df2fea7d14b2f1da2062fbb1a0a))
* **queue,logging:** propagate request log context into job logs ([52fe883](https://github.com/mohamed-rekiba/arvel/commit/52fe88313041645237284ae81e4eb8fb5fea918d))
* **queue,mail,search,broadcasting:** typed driver enums + DLQ docs ([b425cb5](https://github.com/mohamed-rekiba/arvel/commit/b425cb5df3a1d89f9998bd49b48cb9c6f5161406))
* **resources:** unified resource lifecycle & health checks (DR-0039) ([2104ff8](https://github.com/mohamed-rekiba/arvel/commit/2104ff87d6225891858bcb52a6ebb3a7801f78b9))
* **routing:** .hidden() to exclude a route from OpenAPI; single typed /health ([968585e](https://github.com/mohamed-rekiba/arvel/commit/968585e91fa4bfad6b28aba4ba286f0dd475cd20))
* **routing:** warn at startup when public_dir is set but index.html is missing ([83bb881](https://github.com/mohamed-rekiba/arvel/commit/83bb8819f22ed22e49e28835935f3803816b166b))


### Bug Fixes

* **errors:** keep 5xx logs concise — no stack wall for deliberate HTTP errors ([dc03801](https://github.com/mohamed-rekiba/arvel/commit/dc038014da4be6e0dcdb262d892d07abbf4fcf9a))
* **errors:** log 5xx server errors (report gap + OTel exc_info bridge) ([9fd3990](https://github.com/mohamed-rekiba/arvel/commit/9fd3990ba191cdb83cb80607804d4d588ba16581))
* **health:** don't leak failure detail on the public /health endpoint ([6dc6702](https://github.com/mohamed-rekiba/arvel/commit/6dc6702a603eca4c283af83bbeadc5d9178d8755))
* **openapi:** serve the docs UI at /docs, not the raw schema ([dbdbaf4](https://github.com/mohamed-rekiba/arvel/commit/dbdbaf42afeb38be0fe48f6d768cb281b5626dc4))
* **queue:** quarantine a poison payload instead of stalling the loop ([5848660](https://github.com/mohamed-rekiba/arvel/commit/5848660f2ce82eca10c429907c0f09b4d7d90509))
* remediate Python-quality audit findings ([b4e11ec](https://github.com/mohamed-rekiba/arvel/commit/b4e11ec4a2c816bb674213f44190bd296bbc0f8c))
* remediate remaining audit findings (round 2) ([3f1b94b](https://github.com/mohamed-rekiba/arvel/commit/3f1b94bcafbce113c443bb001f867f90a6eb9651))


### Documentation

* **auth:** comprehensive authentication overview ([1743005](https://github.com/mohamed-rekiba/arvel/commit/1743005362c020c90bcad31a7b44a7e84bb5bf55))
* fill the gaps a coverage audit found (commands + signing) ([0bf62fd](https://github.com/mohamed-rekiba/arvel/commit/0bf62fdb55bb00e87d9e8886e4d8ec188d762d41))
* fix broken cross-doc anchor (queues → logging correlation) ([3e81524](https://github.com/mohamed-rekiba/arvel/commit/3e8152418bb281686da3e1c78c1ef5b47b398d5a))
* **telemetry:** comprehensive rewrite ([1168c4f](https://github.com/mohamed-rekiba/arvel/commit/1168c4f5c4195e0e3387d9fe041a6db2b2d77d7e))
* update for round-2 changes ([6fe2ef1](https://github.com/mohamed-rekiba/arvel/commit/6fe2ef1f82da805ba6102e10e83122d23117028c))

## [0.63.4](https://github.com/mohamed-rekiba/arvel/compare/v0.63.3...v0.63.4) (2026-07-13)


### Documentation

* explain why API tokens are opaque, not JWTs ([f262f00](https://github.com/mohamed-rekiba/arvel/commit/f262f00974532a4f0d7dcb9486ca6201e28110a9))
* how to import existing password hashes from another app ([77cc799](https://github.com/mohamed-rekiba/arvel/commit/77cc799dad3861d0418b59f4a892941a3aae50d6))

## [0.63.3](https://github.com/mohamed-rekiba/arvel/compare/v0.63.2...v0.63.3) (2026-07-13)


### Documentation

* add the in-repo rewrite map (reference-phrased) so the plan is visible ([4e87332](https://github.com/mohamed-rekiba/arvel/commit/4e87332bca39a5181b53ccc3d4fb5cc49d8f5fda))
* fix grammar artifacts from the name scrub in rewrite-map ([a8732c9](https://github.com/mohamed-rekiba/arvel/commit/a8732c9a5c8bd59e7ac2e714b8d82565d8de0d1a))
* fix the responses.md stream() example — media_type, not headers ([ff3b997](https://github.com/mohamed-rekiba/arvel/commit/ff3b997ad6eeded54ee220c964d836328003960b))
* fix the two runtime-false claims in Getting Started; add gap G-03 ([cdab733](https://github.com/mohamed-rekiba/arvel/commit/cdab7336fc35f54b4f6d81a0370205c03d5873e8))
* fully scrub reference-framework identifiers from the in-repo map; lifecycle telemetry ([b79a8d4](https://github.com/mohamed-rekiba/arvel/commit/b79a8d4182247eb569ded84a4774019b060683cc))
* **rewrite 2:** Getting Started group — structure, deployment, frontend, seeding, config fill ([750b1af](https://github.com/mohamed-rekiba/arvel/commit/750b1afe316ca96f1355bb126cf51a7f0dc62729))
* **rewrite 3:** Architecture — NEW Request Lifecycle page ([2ee7d4c](https://github.com/mohamed-rekiba/arvel/commit/2ee7d4c645336204a0a414ad02c1a4ee9c201699))
* **rewrite 4:** The Basics — NEW Responses page ([8dc41d5](https://github.com/mohamed-rekiba/arvel/commit/8dc41d5974d5ae99bfb5ff908210f0a287cf6c56))
* rewrite and restructure the documentation ([2a2c3bf](https://github.com/mohamed-rekiba/arvel/commit/2a2c3bf689b720330b9bbfb0c92cf1383cb9f2cd))
* rewrite Getting Started in the reference installation shape ([bc8315b](https://github.com/mohamed-rekiba/arvel/commit/bc8315b3ebaee970bcd8880e327816b78ff623ef))
* scrub reference product names from the map (repo brand-token guard) ([286e30c](https://github.com/mohamed-rekiba/arvel/commit/286e30c81a4ca43919408a662bc83b79de09e81f))

## [0.63.2](https://github.com/mohamed-rekiba/arvel/compare/v0.63.1...v0.63.2) (2026-07-12)


### Documentation

* **orm:** close the coverage gaps — accessors/mutators page + eight page gap-fills ([aa977d2](https://github.com/mohamed-rekiba/arvel/commit/aa977d2dde847339223c76932e04ba03213d94ce))
* un-splice the drop_all note from the SQLite batch-alter sentence ([1d6fcfa](https://github.com/mohamed-rekiba/arvel/commit/1d6fcfa91975271ec06e385e2823fcb8780ad6a4))

## [0.63.1](https://github.com/mohamed-rekiba/arvel/compare/v0.63.0...v0.63.1) (2026-07-12)


### Bug Fixes

* **ci:** cooldown belongs to the semgrep exclusion list, not uv resolution ([a69e4f7](https://github.com/mohamed-rekiba/arvel/commit/a69e4f7a2a39daa241d15997012912b595bed31d))
* **ci:** unbreak main — scaffold-deps assertion, throttle time skew, uv cooldown ([7b72142](https://github.com/mohamed-rekiba/arvel/commit/7b7214242b89b72f2d5afd8ac9bb1fe7ee72abb9))
* **console:** standard carries every engine the scaffold defaults to ([5b3bb25](https://github.com/mohamed-rekiba/arvel/commit/5b3bb25234e7a2aa541bab12ab2083157e3e14d2))
* **console:** the scaffold ships its own database driver again ([d6087f4](https://github.com/mohamed-rekiba/arvel/commit/d6087f41b28993d8c694ab2e3c796c4748286ec1))
* **media:** resolve the disk before the reservation row; reject blank disk names ([734345b](https://github.com/mohamed-rekiba/arvel/commit/734345b2281e68ef5e5db95ca04b1e2730a32bd7))

## [0.63.0](https://github.com/mohamed-rekiba/arvel/compare/v0.62.0...v0.63.0) (2026-07-12)


### Features

* enhance the dependencies ([262702e](https://github.com/mohamed-rekiba/arvel/commit/262702eee29cb4edc08ec5da01e4e52b5eac14a3))


### Bug Fixes

* **activitylog:** update snapshots honor __log_attributes__ (no excluded-field leak) ([bc8ce78](https://github.com/mohamed-rekiba/arvel/commit/bc8ce789e4d4fb9ed1fc43c4a7059de23c53ee31))
* annotate the run_due return for strict typing ([94ac857](https://github.com/mohamed-rekiba/arvel/commit/94ac857bd79d6930bcbfae83ab04639d1c8671fd))
* **auth:** a registered policy method takes precedence over a same-named define ([71e2a9d](https://github.com/mohamed-rekiba/arvel/commit/71e2a9db72b818b8d747789139d83b2334a21d30))
* **auth:** policy before() fires whenever a policy exists, on one shared instance ([5e96710](https://github.com/mohamed-rekiba/arvel/commit/5e967105444500b2855633dd0ce6237f5ae5aad0))
* **client:** per-call follow_redirects wins; docs describe the real default ([c792f82](https://github.com/mohamed-rekiba/arvel/commit/c792f82d696a34813a5201dff13d57bbf56159b7))
* **console:** render stubs by literal token substitution, not str.format ([ac71f14](https://github.com/mohamed-rekiba/arvel/commit/ac71f145950fcd890f9ee0c78d651c1a4e9a2527))
* **console:** signature-ordering errors raise at registration, not vanish at build ([8dcfa40](https://github.com/mohamed-rekiba/arvel/commit/8dcfa403b0f6e2aaa461aab142dca6c6ccc42c96))
* **http:** the reserved throttle:&lt;name&gt; form resolves before the generic alias branch ([b2351e1](https://github.com/mohamed-rekiba/arvel/commit/b2351e110f983c2d83d941a2d92d3aba838c3a4f))
* **http:** the user's preferred locale applies under the real wiring order ([3a99cc1](https://github.com/mohamed-rekiba/arvel/commit/3a99cc18e6aed608cac6429b192cc367f04e1702))
* **media:** resolve the default disk by its real name, not a 'default' placeholder ([ca1adbc](https://github.com/mohamed-rekiba/arvel/commit/ca1adbc915b162ec04bff67ca15c2f1f254c0819))
* **notifications:** a bare on-demand apprise route string is one URL, not characters ([232d2df](https://github.com/mohamed-rekiba/arvel/commit/232d2df333dfee224c0222b26034f264272d6a6b))
* **orm:** morph relations correlate and eager-load with their type discriminator ([f8cceb9](https://github.com/mohamed-rekiba/arvel/commit/f8cceb9810da53abe4321549609acf63cc05c8c4))
* **packaging:** declare typing-extensions — a bare install couldn't import arvel ([18908f6](https://github.com/mohamed-rekiba/arvel/commit/18908f67c59c4744e6e82f570c67f8dca085d00b))
* **queue:** a manual retry gets the job's full tries budget ([07eb986](https://github.com/mohamed-rekiba/arvel/commit/07eb986cda12b212ab5d83961c9cd3e921d1bdf5))
* remove pydantic references and update related documentation ([1afa3c3](https://github.com/mohamed-rekiba/arvel/commit/1afa3c31804ddc014b45fb1fff4b004c95da28b0))
* **scheduler:** standard cron DOM/DOW OR, exact timezone shifts, honest ran-count ([6708fdf](https://github.com/mohamed-rekiba/arvel/commit/6708fdfd084257650953531b463408b8f80a3ec6))
* **scheduler:** Vixie star-prefix rule for the DOM/DOW union ([851cde8](https://github.com/mohamed-rekiba/arvel/commit/851cde8302c10502d3da271e71076ad8c603dd5f))
* **validation:** errors()/validated() run the pass lazily; bail holds on the async path ([0fba2b1](https://github.com/mohamed-rekiba/arvel/commit/0fba2b1c185a32bbc258477d242e51da70e049a3))
* **views,http:** request-scope the flashed errors/old view shares ([4b57652](https://github.com/mohamed-rekiba/arvel/commit/4b57652313e7e1aff508a09f5ca46d3fe8982f1a))


### Refactors

* user_preferred_locale is the public seam Authenticate consumes ([d7fbb2f](https://github.com/mohamed-rekiba/arvel/commit/d7fbb2f342663f4567989752034fa6aa530de96e))


### Documentation

* align four stale passages with the shipped behavior ([25eb932](https://github.com/mohamed-rekiba/arvel/commit/25eb932583278f7b3e6982d5b2d9e822e9700ac1))
* resolve_middleware docstring states the reserved-prefix precedence ([169494a](https://github.com/mohamed-rekiba/arvel/commit/169494acf915741fa098351030efd6ac13e9c944))

## [0.62.0](https://github.com/mohamed-rekiba/arvel/compare/v0.61.0...v0.62.0) (2026-07-12)


### Features

* **console:** finish generator flags + type-safe stubs (CLI-002/003) ([8e37220](https://github.com/mohamed-rekiba/arvel/commit/8e372204687123a880b490dc314ba065be19126c))
* **console:** make:model companion generation (CLI-003) ([9142f3c](https://github.com/mohamed-rekiba/arvel/commit/9142f3cc6786707a34b6bc66e1b5dd0d8f5258ae))
* **helpers,console:** global helpers, Model repr, DumpDie, tinker UX ([5a74279](https://github.com/mohamed-rekiba/arvel/commit/5a74279905566f888d65727f054adda098352450))


### Bug Fixes

* **console:** address CLI-001 review nits ([97f75ed](https://github.com/mohamed-rekiba/arvel/commit/97f75edc2a757670cab5dc747b46a23dcab3a7c6))
* **console:** guard destructive DB commands (CLI-001) ([8432c19](https://github.com/mohamed-rekiba/arvel/commit/8432c190cfa8cece2f395676612c900309386aa8))
* **e2e:** pass --force to db:seed in the smoke script ([76b5de5](https://github.com/mohamed-rekiba/arvel/commit/76b5de51b812df17f9f950f2b2d1063aaef6fc3c))
* **orm:** to_dict() serializes enums, nested values, datetime, UUID (deep) ([5f1649d](https://github.com/mohamed-rekiba/arvel/commit/5f1649d8c5abd2f1789d67517314651cd49e0a17))
* resolve formating issues ([b1fbc38](https://github.com/mohamed-rekiba/arvel/commit/b1fbc38efbd903c4d59863524004fa698a822883))

## [0.61.0](https://github.com/mohamed-rekiba/arvel/compare/v0.60.1...v0.61.0) (2026-07-11)


### Features

* **routing:** first-class websocket routes + built-in broadcast relay ([9f5906c](https://github.com/mohamed-rekiba/arvel/commit/9f5906c9a2346fbf68e3af0540daae73425917bc))


### Bug Fixes

* container treats IO abstract types as non-injectable ([5953b55](https://github.com/mohamed-rekiba/arvel/commit/5953b55393085ae1992b6f3f1b7c625e90d9f8ce))
* decode the request body in the pipeline, after auth (AR-005/AR-006) ([13986ac](https://github.com/mohamed-rekiba/arvel/commit/13986ac4b1050a4eb8f53c7d52177bb19bd61b04))
* FormRequest authorize() runs before the semantic rules layer ([d3578bf](https://github.com/mohamed-rekiba/arvel/commit/d3578bf08dfc84fe843b5a553df408b8b56e9e56))
* invalid-JSON body is a 422, not a 500 (review blocking finding) ([6533063](https://github.com/mohamed-rekiba/arvel/commit/6533063e664aef43739c8018ed6b84a0618c841a))
* **relay:** dead relay task logs + reports instead of dying silently ([446be83](https://github.com/mohamed-rekiba/arvel/commit/446be8396afb9a53e8a93b3b142276ff989e1bda))


### Refactors

* back RBAC roles/permissions with relations, not hand-rolled pivot SQL ([54817a7](https://github.com/mohamed-rekiba/arvel/commit/54817a78ac85fe7f6d404119a4a04acd0e3d2f94))
* **orm:** morph pivot extras are untyped, matching belongs_to_many ([f022321](https://github.com/mohamed-rekiba/arvel/commit/f022321b7ea394510e6b0e1323f80df8db002043))


### Documentation

* **broadcasting:** the built-in websocket relay + Router.websocket ([4b0bcc4](https://github.com/mohamed-rekiba/arvel/commit/4b0bcc4db69e670d5a96ae5244bc8e483d0262dd))
* **orm:** morph_to_many supports pivot extras + where_pivot scoping ([be947af](https://github.com/mohamed-rekiba/arvel/commit/be947aff4659feb32e8720a619032efbe9f30f5b))

## [0.60.1](https://github.com/mohamed-rekiba/arvel/compare/v0.60.0...v0.60.1) (2026-07-11)


### Bug Fixes

* resolve formatting issues ([506c455](https://github.com/mohamed-rekiba/arvel/commit/506c45571722166ade4cb9693381a03397b0fd43))

## [0.60.0](https://github.com/mohamed-rekiba/arvel/compare/v0.59.0...v0.60.0) (2026-07-11)


### Features

* **dates:** Date.to_iso_string() — the JSON/JS-safe instant form ([523058f](https://github.com/mohamed-rekiba/arvel/commit/523058fe4f36b82214f434f8808142119cf51341))
* **http:** injected FormRequest bodies run the full validation lifecycle ([9728759](https://github.com/mohamed-rekiba/arvel/commit/972875949ed575baa4e1dd8f8bd5b0e52299f4e5))
* **orm:** declarative model observers — __observers__ on the model ([a85d6a8](https://github.com/mohamed-rekiba/arvel/commit/a85d6a8b29ce0f55a8efe974297f92c6a7d3193e))
* **routing:** resource controllers pass as classes, container-instantiated ([4756688](https://github.com/mohamed-rekiba/arvel/commit/47566889ef15cde3a216ccd41528f85011e299f8))


### Bug Fixes

* **i18n:** the framework rides its own catalogs — routing 404 + auth scaffold ([cd58dd3](https://github.com/mohamed-rekiba/arvel/commit/cd58dd34088f0ee61dc17ba1079f0d9250b87615))


### Documentation

* **console:** make:observer scaffold teaches __observers__, not provider wiring ([80ff447](https://github.com/mohamed-rekiba/arvel/commit/80ff447a2f08537af81cdc1fc177ab431cf54dac))
* **console:** make:observer table row teaches the declarative __observers__ form ([dba6f53](https://github.com/mohamed-rekiba/arvel/commit/dba6f53626c236767ccd11a0062b9a5bb597c299))
* cover the round's new capabilities — injected form requests + to_iso_string ([b3fa114](https://github.com/mohamed-rekiba/arvel/commit/b3fa1146b5846eb07bf04317d16eb36e0ce922b7))
* **validation:** note the injected-lifecycle prepare hook constraint ([23074e5](https://github.com/mohamed-rekiba/arvel/commit/23074e58555d95500ab0cd339bfaca81e83c3c78))

## [0.59.0](https://github.com/mohamed-rekiba/arvel/compare/v0.58.2...v0.59.0) (2026-07-10)


### Features

* a queued notification's middleware() receives the recipient and channels ([5ae588a](https://github.com/mohamed-rekiba/arvel/commit/5ae588a8a354e1a2d9afa32261c07514adbaac03))
* aggregate all validation errors, session flash verbs, one authorize-fail 403 type ([aee174b](https://github.com/mohamed-rekiba/arvel/commit/aee174be690c4f4729fa4e14165e79c7bd6bd941))
* complete E6 routing surface — router, model bindings, docs, tests ([fa0955e](https://github.com/mohamed-rekiba/arvel/commit/fa0955ef5e1f9744567ee32934dfc9d821c3d6e8))
* conditional binds, contextual give_tagged/give_config, variadic injection ([e01cc83](https://github.com/mohamed-rekiba/arvel/commit/e01cc83545b4734628fb5c2bfc54b34c58bc1991))
* context bulk/conditional ops, full hidden mirror, hidden-aware scope ([f39a9cf](https://github.com/mohamed-rekiba/arvel/commit/f39a9cff928195563dd0eec68a255f6f41d0924d))
* declarable notification middleware + document the queued/delayed rails ([822f726](https://github.com/mohamed-rekiba/arvel/commit/822f7263f8a358aac5a4bff336aaaa0546436be0))
* domain routing, scoped/trashed bindings, current-route, middleware priority ([c93b405](https://github.com/mohamed-rekiba/arvel/commit/c93b405bba2101b8f7c226aa8659a6bcce99ce8d))
* environment matcher, typed config, declarative providers, container-held registries ([6416812](https://github.com/mohamed-rekiba/arvel/commit/641681238d3110c7dbd0e00dcaf471c3c0467d93))
* exception-handler levels, predicate suppression, throttling, self-handlers, global context ([7a41acb](https://github.com/mohamed-rekiba/arvel/commit/7a41acb3e915df6aa6834d8d8a06d893532428ab))
* factory has_attached + unify the relation-proxy surface ([e51b3b3](https://github.com/mohamed-rekiba/arvel/commit/e51b3b3005e595c59a3ca7bae507c63e5506d018))
* HTTP client peripherals — redirect/TLS opt-outs, sink, url params, macros ([453e720](https://github.com/mohamed-rekiba/arvel/commit/453e7205018ca06dcd95d990562c36e861540b85))
* nested JSON:API includes, when_counted/when_pivot_loaded, to_dict date ISO ([0a5bfda](https://github.com/mohamed-rekiba/arvel/commit/0a5bfda036e0e9b20e06095f1ecfac91a5c09919))
* per-command console signal traps via one shared helper ([7dbbc4a](https://github.com/mohamed-rekiba/arvel/commit/7dbbc4a0242246dd5b7af7730570349d692dd80f))
* public channel-auth verify primitive for broadcasting transport ([269dd22](https://github.com/mohamed-rekiba/arvel/commit/269dd2288d6b788e2fe47fbe33041a6d9a8e874f))
* rich request input surface, input normalization, cookie encryption ([71e019d](https://github.com/mohamed-rekiba/arvel/commit/71e019d4739b4011b706efdb308822bd66583695))
* route groups can declare an OpenAPI security scheme ([202dd3d](https://github.com/mohamed-rekiba/arvel/commit/202dd3db56eaab49f8c8296392ff500bc4ab2e52))
* schema introspection — has_table, has_column, drop_if_exists ([7bd81f3](https://github.com/mohamed-rekiba/arvel/commit/7bd81f3a16fedf18e3aab828f21cce6060825e8d))


### Bug Fixes

* coerce int route keys in binding; unique operationId per method ([0942b5b](https://github.com/mohamed-rekiba/arvel/commit/0942b5b684e5501099d0c68cec0e16d85579756a))
* declare json-cast columns TEXT in skeleton migrations (Postgres agreement) ([97fe29b](https://github.com/mohamed-rekiba/arvel/commit/97fe29b1c1d3936430db31d5eec23b59d8251d20))
* declare query params explicitly instead of the deprecated inferred style ([5e01c19](https://github.com/mohamed-rekiba/arvel/commit/5e01c197754b055423c1657b04dcacaa40c1a400))
* emit OpenAPI parameters in a stable order ([3ee0b4c](https://github.com/mohamed-rekiba/arvel/commit/3ee0b4cbd64405592788a213308a0c982a2c57e8))
* harden email-verification binding and signed-URL base reconstruction ([73ecbaf](https://github.com/mohamed-rekiba/arvel/commit/73ecbafaa3de60e68517ce133adceede6509b40c))
* resolve a missing route-model binding after auth, not before ([27add60](https://github.com/mohamed-rekiba/arvel/commit/27add600c8ff805b3523b44bd4632eca9b10eae2))
* round a sub-second job backoff up instead of truncating it to zero ([4b01816](https://github.com/mohamed-rekiba/arvel/commit/4b01816b6103a0ca46e169b21c7e00ad8a55decc))
* scaffold auth config matches what the guard manager actually reads ([2978673](https://github.com/mohamed-rekiba/arvel/commit/29786732c2d2095113221c0a1e3296b7d1def6ca))


### Refactors

* extract the queue worker loop and serialization; add fail_on_timeout ([d2725f3](https://github.com/mohamed-rekiba/arvel/commit/d2725f3e32dcfb46888fa0982be2f39817cbf8a6))
* split the HTTP kernel, unify throttling, consolidate URL joining ([7d92aa3](https://github.com/mohamed-rekiba/arvel/commit/7d92aa31629f269adb983757dfc55aeaba741ff1))

## [0.58.2](https://github.com/mohamed-rekiba/arvel/compare/v0.58.1...v0.58.2) (2026-07-08)


### Documentation

* 'the [redis] tier' -&gt; 'the [redis] extra' (cache.md) ([df7731b](https://github.com/mohamed-rekiba/arvel/commit/df7731b1babd81012fc2235c2cbb761f7f616875))
* add consistent closing sections across Database + configuration ([42d8bc0](https://github.com/mohamed-rekiba/arvel/commit/42d8bc0d0d2feec913af328f9f4cc022f65350c3))
* add extra callouts for the last inline-only cases (console, media) ([53776e1](https://github.com/mohamed-rekiba/arvel/commit/53776e10681820befe641760a1a908692b9093bb))
* add highlighted [telemetry] extra callout for consistency ([0620fd9](https://github.com/mohamed-rekiba/arvel/commit/0620fd9bd48180bb43073e12465f5f8bd690963c))
* add scoped [jwt] callout to guards for full consistency ([83a27e3](https://github.com/mohamed-rekiba/arvel/commit/83a27e3017fe3e8cdf8366e67cd93c312492d314))
* add the Broadcasting module page ([95042b0](https://github.com/mohamed-rekiba/arvel/commit/95042b01f8f2f17a473f502bb5d58bf81f1d130e))
* clear reference-framework leaks in auth + routing + relationships ([ecca401](https://github.com/mohamed-rekiba/arvel/commit/ecca40171bf99dc62b383551aa1329439f049987))
* consistency sweep — core phrasing, db handle, json fences ([078d2e0](https://github.com/mohamed-rekiba/arvel/commit/078d2e086043aec8b5cc05142f1beb973f8eb7c9))
* Digging Deeper consistency pass ([5aecff6](https://github.com/mohamed-rekiba/arvel/commit/5aecff6d6113155483864af26f06265c64ace241))
* Digging Deeper rewrite — worked tutorials for money + concurrency ([3da8bc2](https://github.com/mohamed-rekiba/arvel/commit/3da8bc236e37bdd33a91c002536a8793baea557f))
* drop leaked 'story 06' ids + fix garbled features gotcha ([4336b55](https://github.com/mohamed-rekiba/arvel/commit/4336b55106a2052ce6bcd7b55f44fb2b5550b2df))
* final consistency sweep — clear last brand leaks + uniform sections ([4cd81c4](https://github.com/mohamed-rekiba/arvel/commit/4cd81c4e39c6ceb5a1743fa7ae88bf2f0b8b0bf3))
* fix 'pre--9' version-scrub artifact in localization ([5e5f3bc](https://github.com/mohamed-rekiba/arvel/commit/5e5f3bc55cf7c92e99b7d2932176d3d9a3bfa2d3))
* fix brand-scrub artifacts + internal-id leaks across Digging Deeper ([1d38c88](https://github.com/mohamed-rekiba/arvel/commit/1d38c8865d860a2f2576b695798e521fe7ce3cf3))
* fix cross-reference link texts to match new Title Case titles ([be13e23](https://github.com/mohamed-rekiba/arvel/commit/be13e23e039b7af4fda186d9e5cc33ec0cd842ba))
* fix leaked draft note (processes) + misplaced section (hashing) ([045115c](https://github.com/mohamed-rekiba/arvel/commit/045115cf776b69352a2ff1aa1eef70ba897f0296))
* fix PHP-syntax leaks, dangling scrubs, section order ([2800487](https://github.com/mohamed-rekiba/arvel/commit/280048702da41b43cfbaf81a19019964b39924c6))
* ground-up rewrite of the Architecture Concepts module ([c23200e](https://github.com/mohamed-rekiba/arvel/commit/c23200ecbc8fb758c5c042f290865a866c8ddde8))
* highlight required extras consistently on the buried pages ([2facc48](https://github.com/mohamed-rekiba/arvel/commit/2facc48bcc0551d5c5132a68c8db2b24d2d55757))
* lift error-handling page to the docs-quality bar ([78d66a2](https://github.com/mohamed-rekiba/arvel/commit/78d66a284f7004442cadbfc17235e15d10e94afa))
* lift views/pagination to bar + clear brand-comparison artifacts ([21953a8](https://github.com/mohamed-rekiba/arvel/commit/21953a83a134de461acba7093c441b0f1a273409))
* move encryption nonce-budget note out from after 'See also' ([c2b2da0](https://github.com/mohamed-rekiba/arvel/commit/c2b2da08b9b8fc7e7451c5b49b5bf4876e56c997))
* normalize every 'required extra' callout to one template ([318d314](https://github.com/mohamed-rekiba/arvel/commit/318d3143f162ad7893417b00981ff742c4acda0a))
* opinionated rewrite pass — queries + container ([82b44ca](https://github.com/mohamed-rekiba/arvel/commit/82b44ca3b16872d0861cb46579099a9ea297c95c))
* refactor Database & ORM module to the docs-quality bar ([d304f95](https://github.com/mohamed-rekiba/arvel/commit/d304f95aa3ca91bc71235c81139dd052d9a09410))
* restructure the site information architecture ([721f040](https://github.com/mohamed-rekiba/arvel/commit/721f04075a78fd1cadd5534386aff07e7d11b27b))
* Security module consistency pass ([120b6e8](https://github.com/mohamed-rekiba/arvel/commit/120b6e8c40f23a91846c93ad0f000f4f97d786d7))
* standardize all headings to Title Case (H1s + nav labels) ([88e8675](https://github.com/mohamed-rekiba/arvel/commit/88e8675b1ac7dd54bd7642ad20bcce9666488f76))
* strip internal decision-record + audit-finding ids from user prose ([3868373](https://github.com/mohamed-rekiba/arvel/commit/3868373c7a18a8ad0572e0b2deaa957505a14771))
* The Basics rewrite (1/2) — configuration + errors ([4efea66](https://github.com/mohamed-rekiba/arvel/commit/4efea666f38b7aa69057061438332f121a446dc1))
* The Basics rewrite (2/2) — views layouts & inheritance ([4731505](https://github.com/mohamed-rekiba/arvel/commit/473150562db13d7495c64c4d50177fbb2b390039))

## [0.58.1](https://github.com/mohamed-rekiba/arvel/compare/v0.58.0...v0.58.1) (2026-07-07)


### Bug Fixes

* **cache:** drain the owned lock client on app shutdown ([19c8ea4](https://github.com/mohamed-rekiba/arvel/commit/19c8ea47cfd808cc2934bd292644cfc6be23b088))


### Refactors

* **cache:** own the redis lock client instead of cashews internals ([37eaf20](https://github.com/mohamed-rekiba/arvel/commit/37eaf20d1697c8a322df23865667b2f32d67b778))
* **console:** share the signature parser across the layer line ([1acba0e](https://github.com/mohamed-rekiba/arvel/commit/1acba0edf817d802f8dbbe0700de1384bc699323))
* **queue:** extract DurableJobs from the QueueManager coordinator ([bb5ee7e](https://github.com/mohamed-rekiba/arvel/commit/bb5ee7e0f539f18d638272c98d28125ded088bd1))
* **queue:** extract JobRouter from the QueueManager coordinator ([b6ddde8](https://github.com/mohamed-rekiba/arvel/commit/b6ddde8c8b098e9935e1e4173c0d6f958451ce97))

## [0.58.0](https://github.com/mohamed-rekiba/arvel/compare/v0.57.0...v0.58.0) (2026-07-07)


### Features

* **activitylog:** batch grouping and a logging on/off switch ([574d04e](https://github.com/mohamed-rekiba/arvel/commit/574d04e6ec209578deaf85c4d4d91709aef4fd71))
* **cache:** prune tag members so tag sets stay bounded ([be2aca5](https://github.com/mohamed-rekiba/arvel/commit/be2aca5e4b357fb2bbd9c8a0788403bcbe3ab063))
* **inertia:** partial reloads and a real asset version ([70eeed2](https://github.com/mohamed-rekiba/arvel/commit/70eeed2d9cefad309d00096bd7fb014d25a8edd9))
* **mail:** attach from a storage disk and embed inline images ([a3c16e9](https://github.com/mohamed-rekiba/arvel/commit/a3c16e9fd671d8afbd9a70d35899b56e9a1df3ab))
* **media:** video frame extraction and transcode ([c74f4b9](https://github.com/mohamed-rekiba/arvel/commit/c74f4b9fb01e0aa141340c37dbf5146346b3362d))
* **notifications:** structured title/body for push channels ([c29149b](https://github.com/mohamed-rekiba/arvel/commit/c29149bc9e4ad7f341f9bd86b4a97cd433481c52))
* **storage:** signed temporary URLs for gcs and azure ([47d5444](https://github.com/mohamed-rekiba/arvel/commit/47d5444e6119465b14aba0d78a9b13bd3f78e0cd))


### Bug Fixes

* **auth:** equalize login timing for an unknown user ([b440a4e](https://github.com/mohamed-rekiba/arvel/commit/b440a4e8c8b91c9d05edc5205e9c871b8f9b01bb))
* **auth:** token decode requires exp and enforces iss/aud ([30f9056](https://github.com/mohamed-rekiba/arvel/commit/30f9056cf176926a0f12793be477faaa4339abf7))
* **broadcasting:** a metadata-less presence member is authorized ([d6daa81](https://github.com/mohamed-rekiba/arvel/commit/d6daa81f4693319adab7beea7b209069ae8152bc))
* **broadcasting:** evaluate broadcast_when at dispatch for queued events ([c4399f9](https://github.com/mohamed-rekiba/arvel/commit/c4399f94d0af2130995b9990a03a5e5717c36608))
* **http:** default throttle segments by user then IP ([95a8d5d](https://github.com/mohamed-rekiba/arvel/commit/95a8d5d840d8d533cdd4f8c3f4328aa597079e47))
* **http:** Request.validate runs the full FormRequest lifecycle ([b0e558c](https://github.com/mohamed-rekiba/arvel/commit/b0e558c178a61e3d7209141cdd7d27e6ad627efe))
* **i18n:** replace placeholders as whole tokens ([95378e0](https://github.com/mohamed-rekiba/arvel/commit/95378e0879778e93061399fb3b744e863be7637f))
* **inertia:** hash the manifest with sha256, not sha1 ([20768e1](https://github.com/mohamed-rekiba/arvel/commit/20768e13f0b1c95cfc54033c0736396789a87708))
* **orm:** bulk delete respects soft-deletes ([f8e63b5](https://github.com/mohamed-rekiba/arvel/commit/f8e63b55ead5d758009ceca6d2245b4657df4363))
* **orm:** coerce non-temporal cursor values back to the column type ([817d563](https://github.com/mohamed-rekiba/arvel/commit/817d563b04865e570b8f2bf16a0e6f2633585b8d))
* **orm:** where_not_in/or_where_in adapt values like where_in ([409cc19](https://github.com/mohamed-rekiba/arvel/commit/409cc19a8fc508a373bbc016e2ba61e11b7f60ee))
* **queue:** a unique job's delayed dispatch can't double-enqueue ([239e768](https://github.com/mohamed-rekiba/arvel/commit/239e768583acdab656af823ce5c71bcf16332d60))
* **queue:** run a filtered job when there's no durable store ([c35ee6b](https://github.com/mohamed-rekiba/arvel/commit/c35ee6b8704c2cb568df4dab3a255de0aa235bc1))
* **validation:** await custom async rules on the async path ([86e06bf](https://github.com/mohamed-rekiba/arvel/commit/86e06bf283119ac6c48a1eea25feb9d59c6aa386))

## [0.57.0](https://github.com/mohamed-rekiba/arvel/compare/v0.56.0...v0.57.0) (2026-07-07)


### Features

* **console:** exit codes from handle(), fail(), missing-input prompting ([ceaae8a](https://github.com/mohamed-rekiba/arvel/commit/ceaae8a715d4a268c3bbf0ea7c764ad4f85c1a06))
* **database:** generically typed ORM read surface ([8434c37](https://github.com/mohamed-rekiba/arvel/commit/8434c3740485b33cbb2f9d4355cdb91db3842741))
* **database:** query-builder parity verbs and factory fills ([4f6487a](https://github.com/mohamed-rekiba/arvel/commit/4f6487adb116b63b739b4a44d9bffee4d7762a4d))
* **dates:** multi-format parse with typed error, localized diff_for_humans ([e820794](https://github.com/mohamed-rekiba/arvel/commit/e820794643a0fc17840df56ecd36f0db8822169c))
* **http,routing,client,views:** atomic throttling, routing fills, client retry surface ([42a7503](https://github.com/mohamed-rekiba/arvel/commit/42a75035cbba9b7262a35059770c2d896a3e06b5))
* **mail,notifications:** transactional queued rails, failover transports, house idioms ([4cf2908](https://github.com/mohamed-rekiba/arvel/commit/4cf2908b88cfbb962c547abca5369e7847921736))
* **queue,events,console:** worker queue filtering, queued broadcasts, non-blocking scheduler ([53a0e14](https://github.com/mohamed-rekiba/arvel/commit/53a0e14dd0e3d688c4f0a3e09590e981ac3e2ee6))
* **search,features,filesystem,media,localization,testing:** ecosystem parity pass ([37e5678](https://github.com/mohamed-rekiba/arvel/commit/37e5678c8a0238a344b383a2fc35e95b43f592c4))
* **security:** wire previous app keys into the encrypter ring ([9ec627b](https://github.com/mohamed-rekiba/arvel/commit/9ec627beff6cbdc77cfa40047247449f8afba858))
* **support:** async-aware retry/rescue with reporting, once(), fakeable Sleep ([4a63594](https://github.com/mohamed-rekiba/arvel/commit/4a63594ff5e9d9e27016cfc74897d13f245c79b7))
* **support:** close Str/Collection/Context/Concurrency parity gaps ([04b44e4](https://github.com/mohamed-rekiba/arvel/commit/04b44e47902588cc9a89d32e79bb079c776a4924))


### Bug Fixes

* address the PR-246 automated review findings ([0cb6a22](https://github.com/mohamed-rekiba/arvel/commit/0cb6a2232c464ae90fff8b524adeb57b1e7bab7f))
* **auth,security:** conformance pass — async confirm, typed signer errors, PK-agnostic flows ([92bb56a](https://github.com/mohamed-rekiba/arvel/commit/92bb56a128391deab35c627542e85647e866f1f5))
* **auth:** equalize attempt() timing for unknown identifiers ([f2a869b](https://github.com/mohamed-rekiba/arvel/commit/f2a869b43342eea55978b348aaf2f5b8878a0b14))
* **cache:** stored None is a hit; events, batch verbs, lock conveniences ([1b48d4f](https://github.com/mohamed-rekiba/arvel/commit/1b48d4fbba9a7b54ecf433ef6ec2b98bdbfabe3a))
* **console,auth:** resolve the reset sweep through the container, restoring G2 ([a2c0c9b](https://github.com/mohamed-rekiba/arvel/commit/a2c0c9b6dcb5cb6a21b39378091a9599a107e5e0))
* **database:** dirty-only saves and the instance CRUD surface ([84da396](https://github.com/mohamed-rekiba/arvel/commit/84da3965ed2d951c2088513e66e2bb6e3a8daa81))
* **database:** raw select/statement/stream join the active transaction ([22cf003](https://github.com/mohamed-rekiba/arvel/commit/22cf003161060e5eaae0f909b2400c7555bbe583))
* **database:** shape-correct relation eager loads, correlations, morph map ([3c50948](https://github.com/mohamed-rekiba/arvel/commit/3c5094844ab38ec68b9481071321b226f87d9a2d))
* **database:** trashed queries are full-fidelity model queries ([aac0a77](https://github.com/mohamed-rekiba/arvel/commit/aac0a77fb1c1120dd1d5767b1a423d4de98c5dd8))
* **http:** render errors at their real status; one HTTP-error vocabulary ([0fbecbe](https://github.com/mohamed-rekiba/arvel/commit/0fbecbe720c69ebf38e2bc4d28777e4480bae557))
* **kernel:** base_path-anchored discovery, .env.[APP_ENV] overlay, typed ProviderInput ([aa16c25](https://github.com/mohamed-rekiba/arvel/commit/aa16c25219b513dc1a842ae85f35661e57dbc22c))
* **kernel:** container rebind, hooks, positional-only call, contextual primitives ([ef448f1](https://github.com/mohamed-rekiba/arvel/commit/ef448f112f8cec077ab39cbea8e454f419b217da))
* **mail:** attachment reads leave the event loop ([dbf7fc5](https://github.com/mohamed-rekiba/arvel/commit/dbf7fc52964411c6687489727e7502112097b632))
* **queue:** a filtered broker delivery is parked durably, never dropped ([d357a82](https://github.com/mohamed-rekiba/arvel/commit/d357a82a83cb4773d28bbda68b175eb33ed52788))
* **validation:** one 422 error contract for both engines ([47e45f5](https://github.com/mohamed-rekiba/arvel/commit/47e45f5e501a5a49b91dd9e25b626be4c323c96d))


### Refactors

* **contracts:** one typed model-host contract replaces the mixin ignore clusters ([e5fed29](https://github.com/mohamed-rekiba/arvel/commit/e5fed29f367244dec4ced6c4897b5ba37e4522e4))

## [0.56.0](https://github.com/mohamed-rekiba/arvel/compare/v0.55.2...v0.56.0) (2026-07-06)


### Features

* **database,http:** JSON:API resource documents ([b895414](https://github.com/mohamed-rekiba/arvel/commit/b895414074e7e5a22db113f36a98a09abe76e0c4))
* **database:** vector-similarity clauses on the query builder ([07d7b00](https://github.com/mohamed-rekiba/arvel/commit/07d7b00b3fb515481e89ed6397a9b42d0710d375))
* **http:** origin-aware request-forgery verification ([25008b1](https://github.com/mohamed-rekiba/arvel/commit/25008b1545ecfaabc4932a2e52422b2e23abf15b))
* **queue,events,database:** one after-commit seam for events and jobs ([6f6e792](https://github.com/mohamed-rekiba/arvel/commit/6f6e79294e9a1f04d405348e6abc58e8cb8a8cbf))
* **queue:** central per-class queue routing ([e1e7301](https://github.com/mohamed-rekiba/arvel/commit/e1e7301a065705ac434d30669e297743c90c324f))


### Bug Fixes

* address external review findings across the round's seams ([d03291e](https://github.com/mohamed-rekiba/arvel/commit/d03291e56911c33152725146bc4454e3cfb72add))
* **client:** key the keep-alive registry weakly on the loop object ([f803ae5](https://github.com/mohamed-rekiba/arvel/commit/f803ae5090ea5d2661b368763d735d6cc8044665))
* **routing:** keep public-root path probes off the event loop ([b980ca7](https://github.com/mohamed-rekiba/arvel/commit/b980ca701a3efd5c4c196132b6f50d3fbd1c9215))


### Refactors

* brand-free tree — neutral public names and generic prose ([5d9b36b](https://github.com/mohamed-rekiba/arvel/commit/5d9b36b11523d8429b20a25ba215ffb1f8a19f7c))

## [0.55.2](https://github.com/mohamed-rekiba/arvel/compare/v0.55.1...v0.55.2) (2026-07-06)


### Documentation

* correct ok() semantics and document wildcard listener signature ([f8bae2c](https://github.com/mohamed-rekiba/arvel/commit/f8bae2c9ac30b02cd6c6008c4301c47b3f6787ff))

## [0.55.1](https://github.com/mohamed-rekiba/arvel/compare/v0.55.0...v0.55.1) (2026-07-06)


### Bug Fixes

* address automated PR review findings ([8c12266](https://github.com/mohamed-rekiba/arvel/commit/8c1226661c83cfc631fbcb4dfb2a594792a2bedb))
* **auth:** high-entropy 2FA recovery codes; atomic remember-cookie rotation ([989e695](https://github.com/mohamed-rekiba/arvel/commit/989e69574701e4884bf2b43a92a977e8f9aafe8d))
* **cache:** a non-positive TTL evicts and stores nothing, not forever ([264adb0](https://github.com/mohamed-rekiba/arvel/commit/264adb0f62032ee81ca390c0c8d312f46682b413))
* **client:** ok() means exactly 200, not the whole 2xx range ([a43414c](https://github.com/mohamed-rekiba/arvel/commit/a43414ccd3c2190e34ef21e2fcc22be237d20958))
* **database,scheduler:** fire update lifecycle on increment; guard cron step ([18e303f](https://github.com/mohamed-rekiba/arvel/commit/18e303f8738d9e7ebf547bce19e436207565714a))
* **database:** correct morph_to eager-load, mass-update timestamps, count, increment, exists ([28875c5](https://github.com/mohamed-rekiba/arvel/commit/28875c53950ff764456fd1a1a8a94c9e8ee2e19e))
* **events:** wildcard listeners receive the event name first ([75ba254](https://github.com/mohamed-rekiba/arvel/commit/75ba254150a7ea07e70cc1bf9713a1b3de18c90b))
* **filesystem:** delete() of a missing path is an idempotent success ([5065e5a](https://github.com/mohamed-rekiba/arvel/commit/5065e5a2afedabcfb3e9681adbaadc1e047d7200))
* **http,routing:** persist late session flash, honor route-key URLs, encode paths, close backslash redirect ([f6a0219](https://github.com/mohamed-rekiba/arvel/commit/f6a0219c234cc15a412f22ab681445ff3226a36f))
* **scheduler:** hold the one-server claim for the whole minute; parse stepped/named cron ([016b881](https://github.com/mohamed-rekiba/arvel/commit/016b881a3640b600d53282a625781f918489f146))
* **support,kernel,localization:** correct edge-case behavior on collection/container/plural paths ([f0b6c27](https://github.com/mohamed-rekiba/arvel/commit/f0b6c27428d1253351984152c32f9e81bcac150a))
* **validation:** tighten boolean set, dot-path cross-field refs, ASCII digits, nullable ([f3a637d](https://github.com/mohamed-rekiba/arvel/commit/f3a637d2e731ef28b96ae87b77fccba554d171e9))

## [0.55.0](https://github.com/mohamed-rekiba/arvel/compare/v0.54.0...v0.55.0) (2026-07-06)


### Features

* **config,dates:** env() quote-stripping + common Date accessors ([14cfa31](https://github.com/mohamed-rekiba/arvel/commit/14cfa311318ca6439ba6ea47947798e114ba0623))
* **features,activitylog:** ship migrations + purge-all/values ([03485ef](https://github.com/mohamed-rekiba/arvel/commit/03485ef75fabf55d9910070aea3da95c2a3b7af8))
* **http:** rate-limit headers on default throttle + request input helpers ([52b717f](https://github.com/mohamed-rekiba/arvel/commit/52b717f3d98f7c8020eeb375e80dbd30a15c5af3))


### Bug Fixes

* address automated PR review findings ([392b2f0](https://github.com/mohamed-rekiba/arvel/commit/392b2f07858c84ffe656d39ce34e3ad67f23b6e8))
* **auth,security:** offload blocking hashing and JWKS fetch off the event loop ([91fccab](https://github.com/mohamed-rekiba/arvel/commit/91fccabf59edefe5a8244536aa4b1daf3c662eb8))
* **cache:** has() checks existence, not truthiness ([f50d0d6](https://github.com/mohamed-rekiba/arvel/commit/f50d0d67021b90682fcbace8df441ff4df7fadc1))
* **client:** reuse a keep-alive connection across sequential calls ([200da9b](https://github.com/mohamed-rekiba/arvel/commit/200da9b68686d92d3c48097330b9913c1d5d4bf7))
* **database:** retry only transient txns; count() via COUNT not full load ([dbdaccd](https://github.com/mohamed-rekiba/arvel/commit/dbdaccd9b62d8869c9eb7ffd08ea07f139dd45df))
* **database:** support non-integer primary keys in relations and chunking ([c1e86ed](https://github.com/mohamed-rekiba/arvel/commit/c1e86edb42f576967072795912632217f92ffccf))
* **http,database:** address review nits ([7dd6fc2](https://github.com/mohamed-rekiba/arvel/commit/7dd6fc2a180d176d63d9b99ab165a3b04f04b538))
* **localization:** longest-first placeholder replace + choice selectors ([4649d40](https://github.com/mohamed-rekiba/arvel/commit/4649d40e920368fa27053be723d909150902c0ad))
* **media,routing:** offload blocking I/O off the async request path ([b87ca4a](https://github.com/mohamed-rekiba/arvel/commit/b87ca4a59c8da5a4403eec3bada93acc8b69cced))
* resolve formating issues ([5bdbb5b](https://github.com/mohamed-rekiba/arvel/commit/5bdbb5b8aaaaa1dea48a1b06b47f4ed971d31bb1))
* **search:** encode bool/None filter values as engine literals ([ac56d08](https://github.com/mohamed-rekiba/arvel/commit/ac56d084bf8972da842726dd70a0b54296dc2ff9))
* **validation:** run custom Rule/Enum objects on the sync path ([5ce3a64](https://github.com/mohamed-rekiba/arvel/commit/5ce3a647757b4e7f2c8355508c2ee57f4e8db88d))


### Documentation

* **broadcasting:** correct stale provider docstring ([d17ba93](https://github.com/mohamed-rekiba/arvel/commit/d17ba9361240ace5f00039177778955688e76a18))
* cover this round's public-API changes ([ea32ef3](https://github.com/mohamed-rekiba/arvel/commit/ea32ef39ac371cba550285258409cec985e6dfbd))

## [0.54.0](https://github.com/mohamed-rekiba/arvel/compare/v0.53.0...v0.54.0) (2026-07-05)


### Features

* **console:** seeders get the command output handle (progress bars) ([e2330a3](https://github.com/mohamed-rekiba/arvel/commit/e2330a3fe8192c49b86fcf51f87a40d3e1ca96cf))

## [0.53.0](https://github.com/mohamed-rekiba/arvel/compare/v0.52.1...v0.53.0) (2026-07-05)


### Features

* **application:** add metrics route if metrics are enabled ([eed83cb](https://github.com/mohamed-rekiba/arvel/commit/eed83cb6882a8dae9c7fe1bf57e6860d3c9ebb32))
* **application:** add support for custom .env file path and enhance JWT secret validation ([65fc33f](https://github.com/mohamed-rekiba/arvel/commit/65fc33f56a25fd382ccd98e5851b621d46bd65d1))
* **arvel:** port LogManager + harden Container, Session, and Auth ([bf41e56](https://github.com/mohamed-rekiba/arvel/commit/bf41e565f8b07cf58565f7504a29ef294025cb03))
* **arvon:** add fluent datetime layer over whenever ([e204e81](https://github.com/mohamed-rekiba/arvel/commit/e204e81067ed9fab1aa5c1d29f5ec62913f05621))
* **auth:** HasRoles.remove_role — revoke a role (Spatie removeRole parity) ([733510c](https://github.com/mohamed-rekiba/arvel/commit/733510ca99490445eef8f56a94d6e57124c8ecc6))
* **auth:** permission guards accept a list with all/any semantics ([6ed283e](https://github.com/mohamed-rekiba/arvel/commit/6ed283eb93d9ad5b26560fe0a9cef9c46dd45e68))
* **auth:** policy discovery + Gate guest-deny + Sanctum completeness + Fortify 2FA ([8b2c7fd](https://github.com/mohamed-rekiba/arvel/commit/8b2c7fda0a7968038a1c3fa7d40b2d37e8556a4b))
* **auth:** revoke access tokens and share the login throttle ([c27ce83](https://github.com/mohamed-rekiba/arvel/commit/c27ce83eb3fe167d498449dfd86fd66293113bc8))
* **auth:** Role.permissions() — a role's granted permissions (Spatie parity) ([95cfada](https://github.com/mohamed-rekiba/arvel/commit/95cfada89cca35f1e463fb9ea454da8457ed5135))
* **auth:** session login security + single-use password-reset broker + email-hash verification ([4de7c41](https://github.com/mohamed-rekiba/arvel/commit/4de7c4149ba97ee3d7b4aac6e3325be9ea8e01ad))
* **boundaries:** enforce the module DAG via import-linter layers (empty allowlist) ([162f360](https://github.com/mohamed-rekiba/arvel/commit/162f3603deadd93f8d55479336935a28ca1ae3b8))
* **broadcasting,mail,notifications:** channels+auth, multipart/markdown mail, notification broadcast ([4508a65](https://github.com/mohamed-rekiba/arvel/commit/4508a65b5ae195f6b0820d2167cf2ba39edc7fe0))
* **cache:** full verb set + owner-tokened locks + tags + Redis facade ([d50d6b0](https://github.com/mohamed-rekiba/arvel/commit/d50d6b0d5576c62e72e75b678bc5c7475393ec02))
* **cli:** auto re-exec global arvel into project .venv ([8332713](https://github.com/mohamed-rekiba/arvel/commit/8332713185f9a741caf31b4974ac54d93d2cac8a))
* **client:** Client.timeout() chainable (parity with base_url/with_headers) ([709f470](https://github.com/mohamed-rekiba/arvel/commit/709f470a12a417c8c0d875413cf2c7cada077fff))
* **client:** HTTP-client parity — builders, response wrapper, pool, fake ([a9ed3bc](https://github.com/mohamed-rekiba/arvel/commit/a9ed3bc91c6655b9e5268ac1e176477313c575ed))
* **cli:** needs-based subsystem bootstrap ([82aa7fa](https://github.com/mohamed-rekiba/arvel/commit/82aa7fac6c39eed99a54a0dd1a2083f8d0be5454))
* **cli:** show boot spinner during framework startup ([94b6351](https://github.com/mohamed-rekiba/arvel/commit/94b63518f7ff1347091352dbd224f2cff3f661c7))
* **console:** A8 scaffold-name fix + I/O, prompts, signature grammar, Artisan.call, maintenance, stub:publish ([3a96de9](https://github.com/mohamed-rekiba/arvel/commit/3a96de9754bd79cfd928d70b4013eed1cb46f54d))
* **console:** add missing Laravel commands (migrate:fresh/refresh, db:wipe, cache:clear, key:generate, storage:link, make:enum/exception/test) ([3014f09](https://github.com/mohamed-rekiba/arvel/commit/3014f09a518195ed575cbbba8a13ab4d3e5d6059))
* **console:** make:event, make:listener, make:cast generators ([e26beac](https://github.com/mohamed-rekiba/arvel/commit/e26beacb8bd257b244891c48e70106b15033bf72))
* **console:** openapi:export — render the OpenAPI document to a file ([52191e1](https://github.com/mohamed-rekiba/arvel/commit/52191e19f4cb1fb61953f9f618327428450767c7))
* **console:** plain ASCII banner on bare `arvel`, no color ([755fcba](https://github.com/mohamed-rekiba/arvel/commit/755fcba2f0de8a2e78061dfc0f1ed5a1957e496b))
* **console:** unify programmatic dispatch through Typer ([42e5979](https://github.com/mohamed-rekiba/arvel/commit/42e5979624cc2d8729526c4949d582f2f9d58129))
* **database:** EloquentCollection, QB breadth, dialect upsert + diff sync, cursor pagination ([45ce2b8](https://github.com/mohamed-rekiba/arvel/commit/45ce2b8b94986c32b86f79548832cbd6271ef673))
* **database:** model observers + fix queued binary attachments over a real broker ([6ec8e7d](https://github.com/mohamed-rekiba/arvel/commit/6ec8e7d0f99547296a76164c8cc21cc8fbbbc7e1))
* **database:** schema evolution + seeder controls + relationship factories ([71ec98a](https://github.com/mohamed-rekiba/arvel/commit/71ec98a63f13cd4d5da306fc65a39c3b713cf80b))
* **database:** Schema.table + drop_column (Laravel Schema::table); server-side defaults ([0ad3146](https://github.com/mohamed-rekiba/arvel/commit/0ad31465872e2b78f58c56ab7245b181fb2834c3))
* **database:** store datetimes as real DateTime values, not ISO strings (DR-0023) ([c15c846](https://github.com/mohamed-rekiba/arvel/commit/c15c84682e27bf041f4d744d8d80c5c6f66715e2))
* **database:** where() gains the 'ilike' operator ([125b557](https://github.com/mohamed-rekiba/arvel/commit/125b557566c20b2c816bf096f68cc27f0afc25bd))
* **dates:** Date instances order naturally (Carbon parity) ([cd32372](https://github.com/mohamed-rekiba/arvel/commit/cd32372f949683788189ceda26a030b36391504a))
* **db,http,client:** add builder/accessor capabilities the proof-app needed ([fb3b711](https://github.com/mohamed-rekiba/arvel/commit/fb3b711c78cbc8f46dd47e42b74d7f35ed1d0327))
* **docs:** restructure documentation with new architecture and lifecycle files ([c18ed3c](https://github.com/mohamed-rekiba/arvel/commit/c18ed3c9cd2315cf2f3d22434840909862c56b97))
* **ecommerce-kit:** aggregate admin dashboard stats at the DB ([2c46f51](https://github.com/mohamed-rekiba/arvel/commit/2c46f5162c0b1dc8b337b8e38de06777011b3195))
* **ecommerce-kit:** cosmic hero and storefront animation layer ([ff6c317](https://github.com/mohamed-rekiba/arvel/commit/ff6c317e8e47c946f5c5c8d3aa5e1bd3199a3d8f))
* **ecommerce-kit:** customer-role listener, cart stock lock, checkout guard ([f7b2b01](https://github.com/mohamed-rekiba/arvel/commit/f7b2b01dec57feebba7182166287212b12b48c5b))
* **ecommerce-kit:** persist the storefront wishlist for guests ([183430b](https://github.com/mohamed-rekiba/arvel/commit/183430b6cbd9b07127ac6acdf3dd511c1c082509))
* **ecommerce:** add suspend/reinstate controls to admin user detail ([573de13](https://github.com/mohamed-rekiba/arvel/commit/573de133b5b2a5d1bb91843c98d22232fbb2a682))
* **ecommerce:** derive is_new from created_at instead of hardcoding false ([f450cc7](https://github.com/mohamed-rekiba/arvel/commit/f450cc71770eb86f43d1a4dcb1abda20581bb3c2))
* **ecommerce:** give product cards soft resting elevation ([0bb73fa](https://github.com/mohamed-rekiba/arvel/commit/0bb73fa7cfce653cd64d5ddc3588080ea34b4cd5))
* **ecommerce:** refresh design foundation — display font + soft elevation ([56ad1d0](https://github.com/mohamed-rekiba/arvel/commit/56ad1d07ea87bd458310978086d074d009878bab))
* **ecommerce:** seed sample orders so best-sellers has data ([2243901](https://github.com/mohamed-rekiba/arvel/commit/22439014ef8babd4b575498259952bf09665c939))
* **ecommerce:** storefront filter searches the full catalog ([133863f](https://github.com/mohamed-rekiba/arvel/commit/133863f24a66e7125baa5492785b286efc7137e3))
* **extras:** add an 'oidc' optional-dependency extra (pyjwt[crypto]) ([14396bb](https://github.com/mohamed-rekiba/arvel/commit/14396bbc98dd0f1be4fe58c276291d36c44faf3a))
* **features:** Pennant-style feature flags (array/database/cache drivers) ([1dcab2f](https://github.com/mohamed-rekiba/arvel/commit/1dcab2fbe0fce23b3d89049d15087ebb7a17cda5))
* **filesystem:** full Storage surface + visibility + fake ([dc5acf8](https://github.com/mohamed-rekiba/arvel/commit/dc5acf8075a66e6d880f691732d3917b8bcde439))
* **foundation:** harden container/app/console and wire the token guard ([5a76889](https://github.com/mohamed-rekiba/arvel/commit/5a768895899bf38daac57cf1bad34b20022495a1))
* **http:** add Http facade and Http.fake outbound client ([097098f](https://github.com/mohamed-rekiba/arvel/commit/097098f00183f8d15dc26a1762c14baf79e2ef85))
* **http:** add response() and redirect() helpers ([2cdf841](https://github.com/mohamed-rekiba/arvel/commit/2cdf841826b11ae4face016b282d919def72056a))
* **http:** consolidate CSRF middlewares and accept more token sources ([57d84a9](https://github.com/mohamed-rekiba/arvel/commit/57d84a9876e59421b8147530226d2bd9d678f1a2))
* **http:** fluent responses/redirects/cookies, url helpers, CSRF except, controller middleware, typed seams ([da1c220](https://github.com/mohamed-rekiba/arvel/commit/da1c2203e9d1a24e548058c93ff9298f77f761b9))
* **http:** HTML form method-spoofing (Laravel [@method](https://github.com/method)) ([81b1a1f](https://github.com/mohamed-rekiba/arvel/commit/81b1a1fce9021e09f5e0025715183792be1878f9))
* **http:** RateLimiter + named throttle limiters with rate-limit headers ([e13f75e](https://github.com/mohamed-rekiba/arvel/commit/e13f75e7cfc74ce05279018e28eaebbe2c105f4f))
* **http:** Redis-backed session store via session.driver config ([0fef79e](https://github.com/mohamed-rekiba/arvel/commit/0fef79e0a3ae3598df9e427c80f5d3a80e3d4892))
* **http:** trust proxies on the general request path ([e6b0d90](https://github.com/mohamed-rekiba/arvel/commit/e6b0d901e022edbc604a0ecc831f9818d313414b))
* **http:** typed query parameters — injected + documented in OpenAPI ([34b82d2](https://github.com/mohamed-rekiba/arvel/commit/34b82d2a3678e9880abf5f9e16af42c4c00bc5e2))
* **i18n:** translatable model attributes (HasTranslations + Translatable cast) ([777276d](https://github.com/mohamed-rekiba/arvel/commit/777276deb97d8da269abebf59c8d34ff81ac7be2))
* **i18n:** translatable model attributes (HasTranslations + Translatable cast) ([392ab7c](https://github.com/mohamed-rekiba/arvel/commit/392ab7ca716d824137cd2b1aa7d550ab4160dcd4))
* **image,orm:** DX-first media API with strict eager-load morph descriptors ([666134c](https://github.com/mohamed-rekiba/arvel/commit/666134cf8742c0e0327c3412f8d727184ef1556e))
* **kernel:** -parity exception handler lifecycle ([d461df6](https://github.com/mohamed-rekiba/arvel/commit/d461df64c5693322d5c3e9c62c667db61e321214))
* **kernel:** with_public_dir/with_lang_dir app-bootstrap overrides ([95d0c82](https://github.com/mohamed-rekiba/arvel/commit/95d0c82a4e8a8b89a5c1d82b9e6f16df6a6b8933))
* **kit:** multiple product images on detail page ([2eded9f](https://github.com/mohamed-rekiba/arvel/commit/2eded9f495342aaf401ca7dc9ac06d591cdc0313))
* **mail:** app-wide default sender (config mail.from) — Laravel parity ([e96587d](https://github.com/mohamed-rekiba/arvel/commit/e96587dab88673230fff8ca6291332a94747b9f2))
* **media:** HasMedia.delete_media — remove ONE item (row + stored files) ([b8a69e2](https://github.com/mohamed-rekiba/arvel/commit/b8a69e2d07f7d2daf1d09cf3072f3a1f2a52fb2a))
* multipart [@method](https://github.com/method), per-app manager config, richer reference app ([d7e29c4](https://github.com/mohamed-rekiba/arvel/commit/d7e29c4cbf7a8672e2b6d0f26fc27498990f428a))
* **openapi:** OpenID Connect security scheme (.secure("oidc")) ([30bbd72](https://github.com/mohamed-rekiba/arvel/commit/30bbd72d716ca566c80982ade72f8263b156ac6e))
* **orm,http:** Laravel-parity relation serialization + conditional clauses ([7ae5798](https://github.com/mohamed-rekiba/arvel/commit/7ae57988fbc4f48bfd12cf4322ba1537f80f02fc))
* **orm,http:** ModelNotFound renders as 404 + export migration Schema type ([29a479a](https://github.com/mohamed-rekiba/arvel/commit/29a479a2b32916d70a824ba590d190d9e7229677))
* **orm:** complete QueryMixin parity and use model query shortcuts ([2f3ebbc](https://github.com/mohamed-rekiba/arvel/commit/2f3ebbc0a118878726d0b1d8888023671d4fd4a5))
* **orm:** enhance eager loading to respect soft delete scopes ([8a9aae8](https://github.com/mohamed-rekiba/arvel/commit/8a9aae87a6c6ccf2ea76a2b204699e3396b48cb7))
* **orm:** per-operation autocommit for Laravel transaction parity ([d750b98](https://github.com/mohamed-rekiba/arvel/commit/d750b9898186c03374902b95d4ec785b57153350))
* **orm:** typed classmethod query entry-points (Model.where/with_/order_by/...) ([ac735d4](https://github.com/mohamed-rekiba/arvel/commit/ac735d47fcbf4da196fd021253b708686d82e850))
* **orm:** where_in accepts a subquery (Laravel whereIn(col, $subquery)) ([79a1276](https://github.com/mohamed-rekiba/arvel/commit/79a12765b94dbe2ea83056f6dc5b1d4abb6c20ae))
* **orm:** where_json_like — LIKE against a value inside a JSON column ([bdd5d06](https://github.com/mohamed-rekiba/arvel/commit/bdd5d0678fcc048d439eeccc046914b57fdcdb87))
* **orm:** where_raw + where_exists (Laravel whereRaw / whereExists) ([013e73e](https://github.com/mohamed-rekiba/arvel/commit/013e73e5a7a6a135b207518df3df453ded311089))
* **pagination:** Laravel-parity paginators (paginate/simple_paginate, links(), JSON) ([2ff86f2](https://github.com/mohamed-rekiba/arvel/commit/2ff86f24e6a30a3febd24df4db360f7affac4fbb))
* **queue:** batching + unique jobs + job middleware + scheduler hardening (A3) ([1901aa0](https://github.com/mohamed-rekiba/arvel/commit/1901aa006505da793bc8a6ffc13871daaff77b1b))
* **queue:** reliability — sequential chains, queued listeners, retry-release, visibility, timeout, worker flags, Context ([11afc42](https://github.com/mohamed-rekiba/arvel/commit/11afc425a26811a5b2653f76bcf6705cf40827d9))
* **routing:** per-route response status override (Route.post(...).status(200)) ([9f0e903](https://github.com/mohamed-rekiba/arvel/commit/9f0e90346f001ece44dda6244d8d5b813a5c1a78))
* **routing:** Router.public() — Laravel-parity public/ web root + SPA fallback ([70a9629](https://github.com/mohamed-rekiba/arvel/commit/70a96295ce64f6980664e128ba688afbf2290360))
* **routing:** signed-URL key defaults to app key + ValidateSignature (signed) middleware ([d447141](https://github.com/mohamed-rekiba/arvel/commit/d447141fb810df601e5f72f5466888974c51b989))
* **scaffold:** ship cache/filesystems/mail config files (Laravel parity + discoverability) ([e77f04e](https://github.com/mohamed-rekiba/arvel/commit/e77f04e7cbd8e611f04b8abdd5a3f76b850d464a))
* **schema:** t.btree_index — composite + expression indexes (jsonb per-locale lookups) ([3e541e4](https://github.com/mohamed-rekiba/arvel/commit/3e541e4e1e9c8d6aba8b0a7c3cdb7a898bdf857a))
* **schema:** warn + degrade Postgres-only DDL on other dialects ([4161e18](https://github.com/mohamed-rekiba/arvel/commit/4161e18c1505f8b8e2c33c6874d54b81f171e737))
* **search:** Scout-parity fluent builder, queued-indexing seam, scout CLI ([058f315](https://github.com/mohamed-rekiba/arvel/commit/058f315df8ecd6d5bc6c117ca0609ae5ee4f2ea7))
* **search:** Searchable.make_all_searchable + remove_all_from_search (Scout parity) ([eff2dd6](https://github.com/mohamed-rekiba/arvel/commit/eff2dd6be92fba37dd360f63022283ebb616f29e))
* **security:** hash driver manager + AES-256-GCM serialize-aware Encrypter ([d23d729](https://github.com/mohamed-rekiba/arvel/commit/d23d7293c71cca23f490660ce847b265c7812d4c))
* **session:** honor SESSION_SECURE/SESSION_SAME_SITE and add typed enums ([b4173ce](https://github.com/mohamed-rekiba/arvel/commit/b4173ce216e1103dc619375e67bf996cd9064321))
* **storage:** implement AzureDriver.temporary_url via SAS token ([591313d](https://github.com/mohamed-rekiba/arvel/commit/591313d53e663d70568fb803df0734e5201950a7))
* **support:** Pipeline, Context, Process, Concurrency + Collection parity ops ([c6b464d](https://github.com/mohamed-rekiba/arvel/commit/c6b464d4a1e0a4c3ed03c47e662f9884a8143118))
* **telemetry:** auto-instrument cache + outbound HTTP, and propagate traces to queue jobs ([07a835f](https://github.com/mohamed-rekiba/arvel/commit/07a835f169551af7ba0bb1f3c2c5d549f0d816d4))
* **telemetry:** auto-instrument database queries with OpenTelemetry CLIENT spans ([41e65d4](https://github.com/mohamed-rekiba/arvel/commit/41e65d496ac5c1a549550fb697e87480c4de9ca3))
* **telemetry:** auto-instrument HTTP requests with OpenTelemetry server spans ([28a8a1a](https://github.com/mohamed-rekiba/arvel/commit/28a8a1ae45505176041ff9623990385ffcae94b7))
* **telemetry:** export metrics and logs alongside traces (full OTLP signal set) ([e7adf38](https://github.com/mohamed-rekiba/arvel/commit/e7adf3853e2c34d9dbe34b7e81915c3e23f8d96c))
* **telemetry:** OpenTelemetry tracing wired from config, backend-agnostic via OTLP ([538efae](https://github.com/mohamed-rekiba/arvel/commit/538efae1d7021dbe9106c1c43f0d47025411d34c))
* **telemetry:** record HTTP request metrics (count + duration) in the middleware ([c73bdbb](https://github.com/mohamed-rekiba/arvel/commit/c73bdbb26d5e61e7f2396c1de73650bd572d2488))
* **testing:** bus/notification fakes + refresh_database + json helpers ([021677b](https://github.com/mohamed-rekiba/arvel/commit/021677b1f51dc722529b0ff75f60e523519fdbfb))
* **testing:** notification/bus/http fakes + response assertions + artisan() helper ([d204d2d](https://github.com/mohamed-rekiba/arvel/commit/d204d2de2e916043eebd40792d42443659633c38))
* **testing:** reset_rate_limiter/reset_sessions for test isolation ([5503547](https://github.com/mohamed-rekiba/arvel/commit/55035475ce11182e12427622160d67db5aa963a7))
* **validation:** A7 url/email fixes + ~35 new rules + FormRequest rules() bridge ([6832e84](https://github.com/mohamed-rekiba/arvel/commit/6832e8495acc3a45eb90e026fb0adceb328eda9d))
* **validation:** add bail, conditional presence, date rules, custom rules, Rule builders ([f06f8d0](https://github.com/mohamed-rekiba/arvel/commit/f06f8d05e44edb117d53b47217a38d9b886ea68f))
* **validation:** support nested and wildcard field paths ([9fe866a](https://github.com/mohamed-rekiba/arvel/commit/9fe866afb5cf58d3f44871356e463155fd85613e))
* **views:** auth()/guest() template globals (Laravel @auth/[@guest](https://github.com/guest)) ([0858d2b](https://github.com/mohamed-rekiba/arvel/commit/0858d2bddcda84c86f1d8ec267bcc6b6a697e2ed))


### Bug Fixes

* **application:** drain every provider on shutdown even when one fails ([275382a](https://github.com/mohamed-rekiba/arvel/commit/275382a06e97d65941604d7c0f52fd33b0af8669))
* **application:** widen Application.make to match Container.make signature ([11c5036](https://github.com/mohamed-rekiba/arvel/commit/11c5036bb918f8296e184c5ff2d17f109f883219))
* **arvel:** correct SyslogChannel handler type under mypy platform pruning ([6a94438](https://github.com/mohamed-rekiba/arvel/commit/6a94438caf22a0845cc48604f36d620582d8a261))
* **arvel:** harden container extend, session guard, cookie expiry, and session lifecycle ([bf466d4](https://github.com/mohamed-rekiba/arvel/commit/bf466d48d11730e4dc9cd47214340db25c00789a))
* **arvel:** inject resend rate-limit store into AuthController ([d244aaf](https://github.com/mohamed-rekiba/arvel/commit/d244aaf26622884984d145deee322aa6473a12d5))
* atomic decrement for batch counters to stop lost decrements ([c764232](https://github.com/mohamed-rekiba/arvel/commit/c76423280dcccb5eaca65d178cc0a4512982d334))
* **audit:** close partial-boot leaks and session/container edge cases ([aa09830](https://github.com/mohamed-rekiba/arvel/commit/aa09830a9eb6972219499e930f8faf885bfc1ee3))
* **audit:** harden container, auth, session, and console boot ([d53bcef](https://github.com/mohamed-rekiba/arvel/commit/d53bcef05d8e3d2b9476715c43835dc95d363a88))
* **audit:** harden lifecycle, container, sessions, and CLI failure modes ([d447ddd](https://github.com/mohamed-rekiba/arvel/commit/d447ddd4a9486310377761a031b4aaaf83e61b9c))
* **audit:** read provider-bound AuditConfig instead of reloading .env per write ([6012528](https://github.com/mohamed-rekiba/arvel/commit/6012528fb76a166d3c5b05932aca83ee9cafd2d5))
* **auth,session:** harden guards, gate, CSRF, and session lifecycle ([5d6f405](https://github.com/mohamed-rekiba/arvel/commit/5d6f4056532bc7aaf028b8443766c33a804989cb))
* **auth:** align password_resets storage name across migration, model, and CLI ([a9aa1c6](https://github.com/mohamed-rekiba/arvel/commit/a9aa1c62eef7a2d2c7d5768d59461d076aaa4e53))
* **auth:** detect refresh-token reuse and revoke the family ([f682950](https://github.com/mohamed-rekiba/arvel/commit/f68295076ca6c9a1745dc706b2ea63d456f2e6b3))
* **auth:** ensure boolean return for post ownership check in PostPolicy ([be42e80](https://github.com/mohamed-rekiba/arvel/commit/be42e8063b03f686e78234aefd20cc7d70e17169))
* **auth:** keep "database" as the canonical provider driver string ([f7f5d85](https://github.com/mohamed-rekiba/arvel/commit/f7f5d855339799956c850749ce42d5da56865f30))
* **auth:** login drops a stale _impersonator_id (defence in depth) ([f44b6e8](https://github.com/mohamed-rekiba/arvel/commit/f44b6e821064eaff41d481d1953e44c03c8dcbfd))
* **auth:** reset access-token per request + bind 2FA challenge to pending user ([fffa098](https://github.com/mohamed-rekiba/arvel/commit/fffa098e604ae05f7d0f74dd3f9ce372a29c56f0))
* **auth:** resolve AuthController per request, not at boot ([ff466e7](https://github.com/mohamed-rekiba/arvel/commit/ff466e7bd630a1fd2f4c1adc3a7e6b6e4baf714b))
* **auth:** return 403 for an unverified logged-in user, not 401 ([b1660f9](https://github.com/mohamed-rekiba/arvel/commit/b1660f974f1f23645ddd9a60e6a73bad7454dbc5))
* **auth:** run policy before() filters in the Gate ([0d74dd3](https://github.com/mohamed-rekiba/arvel/commit/0d74dd37ea93dee08c886ced0576b9ac9ffc6f96))
* **boundaries:** maintenance resolves cache itself (http-&gt;cache legal) ([d4a4326](https://github.com/mohamed-rekiba/arvel/commit/d4a4326dfce8cd3c82ca306f9429867b904ba615))
* **broadcasting,mail:** story-19 hardening nits ([a278bf2](https://github.com/mohamed-rekiba/arvel/commit/a278bf2f161e88bad4d6012fc800bebc55189411))
* **broadcasting:** make the default broadcast payload JSON-safe (WI-012) ([08ff45b](https://github.com/mohamed-rekiba/arvel/commit/08ff45b45d4860b8896e47ba5fa166069f273c35))
* **cache:** a dead Redis raises instead of silently no-oping ([94e7b8c](https://github.com/mohamed-rekiba/arvel/commit/94e7b8c55cae6a27f0dbde04647259fc36f47291))
* **cache:** anchor RateLimiter window to the first hit, not the last ([94b5c02](https://github.com/mohamed-rekiba/arvel/commit/94b5c022e695e03d116eab678f4a06b3f022cc65))
* **cache:** drop stale ttl arg from CacheConfig calls ([dcdba51](https://github.com/mohamed-rekiba/arvel/commit/dcdba51ad019736c7f55e5d64351f0b2db93b651))
* **cache:** redis put(ttl=None) stores forever, drop CACHE_TTL default ([11ad567](https://github.com/mohamed-rekiba/arvel/commit/11ad567b5c5d0f3c27b4e7c1aad6d1af03c3e715))
* **cache:** story-06 review nits ([751e9a1](https://github.com/mohamed-rekiba/arvel/commit/751e9a1e17de95dcd77d6119693230db3e502432))
* **ci/gitleaks:** allowlist valkey image-tag entropy + repair renamed-test path ([e8c40e8](https://github.com/mohamed-rekiba/arvel/commit/e8c40e8536d9e5d60a112161fe393f234437d33a))
* **ci:** pin kit emulator tests to one xdist worker ([ae7e9a6](https://github.com/mohamed-rekiba/arvel/commit/ae7e9a6bbff6d0815330afa7641825ace6d45ac3))
* **cli:** re-exec into project venv and silence shell route logs ([8aac184](https://github.com/mohamed-rekiba/arvel/commit/8aac1843d38c6268bf532abaa9ddb89096964165))
* **config:** make dotted dict lookups key-only ([16790c6](https://github.com/mohamed-rekiba/arvel/commit/16790c6fc71c4d60c0d61d1412f1459046fe843b))
* **console:** --help shows the Laravel colon command names (not hyphenated) ([da14e1b](https://github.com/mohamed-rekiba/arvel/commit/da14e1b13de7de4af24bd0621ee78cac225d4107))
* **console:** annotate venv re-exec nosec suppressions with rationale ([15a340e](https://github.com/mohamed-rekiba/arvel/commit/15a340e9baeae77cdf11b39a3aa100bfea6ffa6e))
* **console:** arvel down/up boot the project app ([d56d387](https://github.com/mohamed-rekiba/arvel/commit/d56d38708ef4ca5bfd68cfaab71966051997e675))
* **console:** constant-time maintenance secret + Artisan.call works from a running loop ([6abe6e9](https://github.com/mohamed-rekiba/arvel/commit/6abe6e961bdc3f7dc4e808486b82d0c1b86e3a61))
* **console:** run async CLI commands on the single event loop ([f30e4d5](https://github.com/mohamed-rekiba/arvel/commit/f30e4d585977e6a327bf29959bdd543f2015061f))
* **console:** run scaffolded compose uv sync from backend/ ([69017d7](https://github.com/mohamed-rekiba/arvel/commit/69017d7da655337111253b19a08b5acd648c8b9f))
* **console:** run uv sync in the kit's python project dir ([2d6fcdb](https://github.com/mohamed-rekiba/arvel/commit/2d6fcdbc21087ba93d6eaad5bce09e623df45aa1))
* **container:** resolve async bindings at any depth in amake ([a2c74ae](https://github.com/mohamed-rekiba/arvel/commit/a2c74ae72cdb3ea0371921c6b95441f3f23e9a20))
* **context:** round-trip hidden data through dehydrate/hydrate ([b355298](https://github.com/mohamed-rekiba/arvel/commit/b355298ddb8ed4e98d325c8e68bd6b47a47ac7f5))
* **database:** bind json key in where_json_path to prevent SQL injection ([364b656](https://github.com/mohamed-rekiba/arvel/commit/364b6568881dff1c0c740160beb295ecdea4a88d))
* **database:** fire retrieved on all read paths; load_missing detects async relations ([9a188c2](https://github.com/mohamed-rekiba/arvel/commit/9a188c2d5d7137f7737557aea2c164005d5c9277))
* **database:** PG column-type fidelity for UUID PKs and json casts ([93d2741](https://github.com/mohamed-rekiba/arvel/commit/93d27418b758458ac13c4b43015b3367e1196b79))
* **database:** raw-select datetime hydration parses SQLite string values ([7d54cca](https://github.com/mohamed-rekiba/arvel/commit/7d54cca3e0ed5493d0be314828b1c34497a905a6))
* **database:** run seeder after-commit callbacks once rows are committed ([534e0aa](https://github.com/mohamed-rekiba/arvel/commit/534e0aaa76e72ab9fa3c8741f62269c28a86a2cb))
* **database:** store datetimes as UTC so SQLite round-trips keep the instant (review B1) ([3d52898](https://github.com/mohamed-rekiba/arvel/commit/3d52898bba6dc3f5faf8b05965c8447b20a01208))
* **database:** story-10 review nits ([69d4398](https://github.com/mohamed-rekiba/arvel/commit/69d439807a6f4b20340f57c9a48b5aa0c1d51cd0))
* **database:** to_dict/to_json unwraps collection/object/stringable/decimal casts ([b2bfe2c](https://github.com/mohamed-rekiba/arvel/commit/b2bfe2c46065ad89d18e8b96eb1c8bdedcd31826))
* **database:** use dialect-aware JsonB/TsVector in column helpers ([356446e](https://github.com/mohamed-rekiba/arvel/commit/356446ef5b0d787cf6970524723db63cf57c1e33))
* **database:** wrap seeders in a database transaction for improved consistency ([b64085e](https://github.com/mohamed-rekiba/arvel/commit/b64085e879635fc8885cb3aabaefab206bc1bfe3))
* **docs:** update link for getting started section in index page ([fb7e4fc](https://github.com/mohamed-rekiba/arvel/commit/fb7e4fc747fa4202f7def34f47df9ba55eed78fc))
* **ecommerce-kit:** 404 on cart PATCH/DELETE for unknown item ([a436600](https://github.com/mohamed-rekiba/arvel/commit/a4366005abf621b2b8b9b4e099f55ceb9731b239))
* **ecommerce-kit:** checkout self-loads the cart on mount ([535845a](https://github.com/mohamed-rekiba/arvel/commit/535845a4048b602dc39b227c6b82d571b52b680a))
* **ecommerce-kit:** fix broken self-service registration flow ([d80dc48](https://github.com/mohamed-rekiba/arvel/commit/d80dc4827bf52d1b741962b83fcbfd4134c23d3b))
* **ecommerce-kit:** gate catalog edit/restore on the update permission ([75e3ee8](https://github.com/mohamed-rekiba/arvel/commit/75e3ee882433f6a0de2ffdfd397b799768125b71))
* **ecommerce-kit:** gate force-delete on role level, not just permission ([8d2f80d](https://github.com/mohamed-rekiba/arvel/commit/8d2f80d5a8c314ca030cb4067eb5d5a1ca8f9c9f))
* **ecommerce-kit:** guard the /admin catch-all route ([6c1d076](https://github.com/mohamed-rekiba/arvel/commit/6c1d076b8aa96eb1c633183e833e3219b50f39e9))
* **ecommerce-kit:** harden admin self-delete and category parent_id validation ([13c0131](https://github.com/mohamed-rekiba/arvel/commit/13c01319feaa020b6839e06ecd4176f09f44340a))
* **ecommerce-kit:** hydrate auth store on guard and unify admin-access check ([b9daf0a](https://github.com/mohamed-rekiba/arvel/commit/b9daf0a25ef0f076ed4321f81eeaba9591c5d74b))
* **ecommerce-kit:** localize admin date/currency formatting ([e9d1338](https://github.com/mohamed-rekiba/arvel/commit/e9d1338f84d2fc59423441ff7f7bc0471b301a84))
* **ecommerce-kit:** localize checkout estimated-delivery date ([c80dfee](https://github.com/mohamed-rekiba/arvel/commit/c80dfee777bd7ca3dca474b25e75d0124cacde1d))
* **ecommerce-kit:** localize storefront listing and search copy ([fcca2f8](https://github.com/mohamed-rekiba/arvel/commit/fcca2f8a5c8efcf8ee430ac7282fdd34cebebcb3))
* **ecommerce-kit:** make seed refresh the catalog view unconditionally ([63bdb05](https://github.com/mohamed-rekiba/arvel/commit/63bdb05a55a32106a2950a42fceb9d6dc94fe4a7))
* **ecommerce-kit:** only confirm an order the account owner placed ([1e524a6](https://github.com/mohamed-rekiba/arvel/commit/1e524a6e86e2c3116b54c688dde6b1fa65b0db78))
* **ecommerce-kit:** order data integrity after force-delete and on checkout totals ([4fceaa4](https://github.com/mohamed-rekiba/arvel/commit/4fceaa4f7f3ce7ba9ab87274dd567434ee3def2c))
* **ecommerce-kit:** point integration tests at testcontainers MinIO ([faafe81](https://github.com/mohamed-rekiba/arvel/commit/faafe8111c2f29f8ce8d0f500b740f7087763a89))
* **ecommerce-kit:** refresh client RBAC on admin navigation ([ca5a753](https://github.com/mohamed-rekiba/arvel/commit/ca5a7535da27a7f588cb81b56b8a737da1d0e93d))
* **ecommerce-kit:** reject category self-parent and parent cycles ([5e65461](https://github.com/mohamed-rekiba/arvel/commit/5e65461ab5ba2e57149df888db1db4e6d1f341d2))
* **ecommerce-kit:** return 404 for admin PATCH on missing product ([8a39d1e](https://github.com/mohamed-rekiba/arvel/commit/8a39d1ee8089dae5e479177a3d7f7a060d165961))
* **ecommerce-kit:** route expired admin sessions to the admin login ([35015dd](https://github.com/mohamed-rekiba/arvel/commit/35015dd11405f88a2dd03c1f229fc856b8856569))
* **ecommerce-kit:** serialize concurrent checkout to prevent duplicate orders ([f2b15ef](https://github.com/mohamed-rekiba/arvel/commit/f2b15ef97100da5dc4af964279d08fbb3e31a712))
* **ecommerce-kit:** show effective permissions on the admin user detail ([40c793f](https://github.com/mohamed-rekiba/arvel/commit/40c793f7c17946ea7a07983e0cb74a985d3571da))
* **ecommerce-kit:** smooth storefront hover and reveal motion ([de03ad1](https://github.com/mohamed-rekiba/arvel/commit/de03ad1c5e704d0666267d923bb8628ab4ceacaa))
* **ecommerce-kit:** snapshot order line names in shopper locale ([be7249e](https://github.com/mohamed-rekiba/arvel/commit/be7249e7ae72196543683de8f195c4e8066f521b))
* **ecommerce-kit:** type and validate the checkout shipping address ([fbdc10c](https://github.com/mohamed-rekiba/arvel/commit/fbdc10c664d51d1ed4d4acfc5f471a62d0a7fc1b))
* **ecommerce-kit:** validate product price/stock bounds and malformed cart ids ([de5917b](https://github.com/mohamed-rekiba/arvel/commit/de5917b78b78eb55d0d80d75368a3488adbd664f))
* **ecommerce/api:** clamp page size on all list endpoints ([75c9ac8](https://github.com/mohamed-rekiba/arvel/commit/75c9ac8dc8d50bd6fc0f3bcd9115cdc2c455c871))
* **ecommerce/auth:** block post-login open redirect ([d02dd04](https://github.com/mohamed-rekiba/arvel/commit/d02dd040c613c9f273c5ded85e5efc96fd13d07f))
* **ecommerce/orders:** bound customer order history pagination ([6aa13e3](https://github.com/mohamed-rekiba/arvel/commit/6aa13e3cb59bc7cf7f3d644b5848fbd58d5e9e3c))
* **ecommerce:** bound and sniff product media uploads ([1a2e415](https://github.com/mohamed-rekiba/arvel/commit/1a2e4156822c651cfdf7344b7ba7cee51217b6ef))
* **ecommerce:** cap product media upload size to prevent memory DoS ([e638ae9](https://github.com/mohamed-rekiba/arvel/commit/e638ae9ec66a4b80e2991c5c7a0280c80e74b7e5))
* **ecommerce:** catalog status enum, cart re-snapshot, force-delete gate ([f946e7a](https://github.com/mohamed-rekiba/arvel/commit/f946e7a581951f31001be7cd1b92a7bc7c28e779))
* **ecommerce:** coalesce catalog refresh so writes aren't dropped ([4c34a24](https://github.com/mohamed-rekiba/arvel/commit/4c34a24a720094ebb1708565fbe5d9c98761a181))
* **ecommerce:** deny-by-default the test seed/refresh endpoints ([d374182](https://github.com/mohamed-rekiba/arvel/commit/d37418235c7121fbfebe6abb085b983a2f1f912a))
* **ecommerce:** drop fabricated dashboard trends and flash-sale discounts ([4d798bc](https://github.com/mohamed-rekiba/arvel/commit/4d798bc74ae7c883750d7db94cd8dc58ecd44536))
* **ecommerce:** drop fabricated discount claims from storefront promos ([587dc24](https://github.com/mohamed-rekiba/arvel/commit/587dc24ba6220d64d1ca6afcecc88625092fa4af))
* **ecommerce:** exclude cancelled orders from dashboard revenue ([8f9df85](https://github.com/mohamed-rekiba/arvel/commit/8f9df85226787edc1ef16311fe21212aefe70610))
* **ecommerce:** extend A01 outrank guard to role/permission mutators ([4185a8a](https://github.com/mohamed-rekiba/arvel/commit/4185a8a45b4d78d2a6969e782708b31cd471a0c1))
* **ecommerce:** gate admin routes by per-feature permission ([3d8feb6](https://github.com/mohamed-rekiba/arvel/commit/3d8feb6b66827fc3b6c4ad18d253d73a63194711))
* **ecommerce:** graceful force-delete with dependent orders ([a46237f](https://github.com/mohamed-rekiba/arvel/commit/a46237f50ccbc0c40342c7c30f3cbfcd36ca3192))
* **ecommerce:** guard admin user lifecycle against privilege escalation ([71df4a7](https://github.com/mohamed-rekiba/arvel/commit/71df4a776797cf4f48597c0c7737fc896d17e9bf))
* **ecommerce:** honor defaultTab so /register opens the register tab ([af40810](https://github.com/mohamed-rekiba/arvel/commit/af40810a20ce8b4c31e6e57e688c1df409c0175a))
* **ecommerce:** improve code formatting and readability ([86fa75c](https://github.com/mohamed-rekiba/arvel/commit/86fa75c429357c5ed3f0d5bc9570dafcf3a340c9))
* **ecommerce:** lock order row on cancel to prevent double stock restore ([8009d9c](https://github.com/mohamed-rekiba/arvel/commit/8009d9c6b78152e8e725d08483d066bc3c5058d2))
* **ecommerce:** manual catalog refresh never reports product_count -1 ([3ad34c1](https://github.com/mohamed-rekiba/arvel/commit/3ad34c1deff74bf3d1a98925d364c2141931b045))
* **ecommerce:** pass placed order id to the account success banner ([ff490f8](https://github.com/mohamed-rekiba/arvel/commit/ff490f8741973820472441d2fab3b68290c3a343))
* **ecommerce:** re-snapshot cart price on quantity PATCH ([7773d5d](https://github.com/mohamed-rekiba/arvel/commit/7773d5d368bee39b8919d7e3c02502570d0aad9f))
* **ecommerce:** reject malformed pagination cursor with 422 ([3b1dfd0](https://github.com/mohamed-rekiba/arvel/commit/3b1dfd05459a7a44722ab170288440b7408c9248))
* **ecommerce:** render real role-permission grants in admin matrix ([e0c55d4](https://github.com/mohamed-rekiba/arvel/commit/e0c55d4e68c9f5726cb624859a6a4bfaf64d30cc))
* **ecommerce:** repair admin contracts and drop fabricated UI data ([7267369](https://github.com/mohamed-rekiba/arvel/commit/7267369f7e0f457e14cb25cd847d3fc3fd55e643))
* **ecommerce:** replace fabricated hero claims with honest copy ([4d2145b](https://github.com/mohamed-rekiba/arvel/commit/4d2145be05405af7d61540eb237a000cee79514c))
* **ecommerce:** report unavailable cart items distinctly from low stock ([e772bc5](https://github.com/mohamed-rekiba/arvel/commit/e772bc58687a4b977afeef733854635f488932e6))
* **ecommerce:** require both view grants for translations endpoint ([3d37e11](https://github.com/mohamed-rekiba/arvel/commit/3d37e11b24dcbea1cf8a287051ec334c033547df))
* **ecommerce:** return 404 when deleting an unknown admin resource ([be57be7](https://github.com/mohamed-rekiba/arvel/commit/be57be7e7c7bd4775ce86e36b3fccb9ae27363a3))
* **ecommerce:** return 409 when force-deleting referenced category/vendor ([5bfa265](https://github.com/mohamed-rekiba/arvel/commit/5bfa26580f5b241aee004b575ef94557f1c07cec))
* **ecommerce:** route cart store error fallbacks through i18n ([8e9b0be](https://github.com/mohamed-rekiba/arvel/commit/8e9b0be250cbd1fc1118e9ba5c007714ea8ac960))
* **ecommerce:** scope storefront search to active category, gate short queries ([ea33fbb](https://github.com/mohamed-rekiba/arvel/commit/ea33fbb13e61adaf79ef3c2c9ce4935e93603386))
* **ecommerce:** show charged snapshot prices in the cart, not live ones ([95458fe](https://github.com/mohamed-rekiba/arvel/commit/95458fe36ea5686ea442535f0f25acbcf529969e))
* **ecommerce:** surface unavailable cart lines instead of ghosts ([77272f1](https://github.com/mohamed-rekiba/arvel/commit/77272f102b8d85999b145f071f65657d18db16c1))
* **ecommerce:** update environment configuration for Docker setup ([6333da9](https://github.com/mohamed-rekiba/arvel/commit/6333da95769edd356b9df42f2a732225fa72af0c))
* **ecommerce:** validate product category/vendor FK at the API ([19a2ac3](https://github.com/mohamed-rekiba/arvel/commit/19a2ac39b816c7ebb43baeae0cd8ab10e8ebf43d))
* **ecommerce:** widen users.name to 255 to match register contract ([cd64546](https://github.com/mohamed-rekiba/arvel/commit/cd6454658f21d9eff3dc8d08346db176f16d587d))
* **encryption:** raise DecryptionError on malformed base64 payloads ([d91a1e6](https://github.com/mohamed-rekiba/arvel/commit/d91a1e6d6d2332070695e61ce8093a9172c9dc0a))
* **events:** log queued-listener enqueue failures instead of running inline ([3a15670](https://github.com/mohamed-rekiba/arvel/commit/3a15670e2c42bdfaf6179d20c2348df8285b72da))
* **filesystem:** contain path traversal — reject ../ escaping the disk root ([219e2f8](https://github.com/mohamed-rekiba/arvel/commit/219e2f8a18ee4a93166bfc83071d98c989bc7d72))
* format code for better readability in telemetry processing functions ([b8ea2dc](https://github.com/mohamed-rekiba/arvel/commit/b8ea2dc2daea5d731729e2e561da7abc899a31ca))
* **foundation:** harden config, container, CLI paths, and scheduler signals ([d3c9de1](https://github.com/mohamed-rekiba/arvel/commit/d3c9de121843dc99d7e3bb64a4bdfad256f69f47))
* **framework:** module-by-module audit hardening (WI-001..010) ([6404515](https://github.com/mohamed-rekiba/arvel/commit/64045152e2135cf1f95bcaa5aaf9e5be190a5710))
* **hashing:** make Hash.check and needs_rehash algorithm-aware ([645b79a](https://github.com/mohamed-rekiba/arvel/commit/645b79a06e4186adb681159e1938dc54c22aacd2))
* **http:** __Host- cookie forces Secure (prefix invariant) ([0c8ce3c](https://github.com/mohamed-rekiba/arvel/commit/0c8ce3c83b36ceddb2adf688d40a509aad0d7793))
* **http:** builder global middleware actually runs on the served app ([551e08e](https://github.com/mohamed-rekiba/arvel/commit/551e08e3f9efa86de02d8e0f678980b7e4c0f55b))
* **http:** map malformed pagination cursor to 400, not 500 ([ffca562](https://github.com/mohamed-rekiba/arvel/commit/ffca562e1cfd0f23d8f335d4e893114cf36a7786))
* **http:** render RFC 7807 problem+json for unhandled errors ([0f162f0](https://github.com/mohamed-rekiba/arvel/commit/0f162f0eaff4c3d4ab24e0a86369a11f939e5d13))
* **http:** run after-commit callbacks after the session is unbound ([4b79e21](https://github.com/mohamed-rekiba/arvel/commit/4b79e21f21399dfbe91ea7344e9271a56975be9d))
* **i18n:** block path traversal in translation loaders ([3af8385](https://github.com/mohamed-rekiba/arvel/commit/3af83851700592d8f0b2f7dbc13eed841fd7b88a))
* **i18n:** select plural form by locale rule, not raw count ([6ef824c](https://github.com/mohamed-rekiba/arvel/commit/6ef824c4ff188872b4c7b6033d43b2b5d0105e3f))
* **i18n:** set_translation stores a dict, not a double-encoded string (review finding) ([d152d9c](https://github.com/mohamed-rekiba/arvel/commit/d152d9c2af7ba1aefca54c58db7aab0db887ee4a))
* **i18n:** Translatable.set returns a dict (JSON column serializes once) ([31b082c](https://github.com/mohamed-rekiba/arvel/commit/31b082c4e253b6cd16b601d5e5faec370739a09c))
* **image:** enforce decompression-bomb guard and add set_max_pixels ([ce57fc4](https://github.com/mohamed-rekiba/arvel/commit/ce57fc4bf4f69e73db0dc72654d4f2f03933c3f4))
* **kernel:** exception-handler review follow-ups ([68a5d42](https://github.com/mohamed-rekiba/arvel/commit/68a5d42872e285127b534e3e3c18145349a80c50))
* **kit/services:** remove hard-coded conversion lists and dead seeder fallback ([9a8cd78](https://github.com/mohamed-rekiba/arvel/commit/9a8cd7833a6169ff75d5a03f91fcf01352c0fbbd))
* **logging:** redact secret log fields by substring ([31586d3](https://github.com/mohamed-rekiba/arvel/commit/31586d301dd3767d32a4f01b6de1bf05a72297b8))
* **logging:** redact secrets nested in dicts/lists, not just top-level keys ([7dace93](https://github.com/mohamed-rekiba/arvel/commit/7dace939962b06c06b0243a5b88d4f197eb8b2a2))
* **mail,notifications:** queued mailables/notifications survive a real broker ([da9c9de](https://github.com/mohamed-rekiba/arvel/commit/da9c9de18b4d0448b5a8463e909d5ba2fa3f29af))
* **mail:** apply global mail.from and render from_name ([347306b](https://github.com/mohamed-rekiba/arvel/commit/347306b85dc16b95ad08cdf3797eef183a9d16e8))
* **media:** convert to RGB before a JPEG conversion (alpha can't be encoded) ([5af20af](https://github.com/mohamed-rekiba/arvel/commit/5af20afc694dc5c8a5ab4e0d15508c2abbcc7a92))
* **migrate:** drop_all drops views/materialized views first (Postgres) ([d65c3cf](https://github.com/mohamed-rekiba/arvel/commit/d65c3cf569ae9083558cc8076228c502d40026b6))
* **migrate:** idempotent migrations + concise CLI errors (no traceback wall) ([80035f8](https://github.com/mohamed-rekiba/arvel/commit/80035f8a05b422d73b8bcdda2101c226c51d5e5a))
* **migrations:** pre-flight DB check in migrate:fresh/refresh ([eb92dfc](https://github.com/mohamed-rekiba/arvel/commit/eb92dfc66a856dc2fb0be454cd8ab4be883c434c))
* **oauth:** default Microsoft email_verified to false when claim absent ([b99d837](https://github.com/mohamed-rekiba/arvel/commit/b99d837d0f4225465c71afa22a59f4e1b577065a))
* **observability:** stop X-Forwarded-For from bypassing /_health and /_metrics CIDR guards ([9a5ad2d](https://github.com/mohamed-rekiba/arvel/commit/9a5ad2d0c01b36ba854d0110601e9ebe62f5bfe6))
* **openapi:** handler docstring becomes the operation description ([8770daf](https://github.com/mohamed-rekiba/arvel/commit/8770daf1a3342197f07a8f522ca974cc36f08e83))
* **orm:** accept Laravel string forms in Model.where/or_where ([f5282dc](https://github.com/mohamed-rekiba/arvel/commit/f5282dcf6053f9cb47a4150ecdf6ec65cf4d4066))
* **orm:** timestamps on by default (Laravel parity) + datetime-safe json cast ([a92c7d8](https://github.com/mohamed-rekiba/arvel/commit/a92c7d8f5f128e3d0b01234bc40ed171d35738cd))
* **orm:** update query syntax for model retrieval to match Laravel style ([aa4429c](https://github.com/mohamed-rekiba/arvel/commit/aa4429c9a097a24c4392c3ab5ebe88d16d680b64))
* **pagination:** address review nits (per_page&gt;=1 guard, list query params, real e2e date proof) ([ce7df61](https://github.com/mohamed-rekiba/arvel/commit/ce7df6123d3751bdba5407332836540343456924))
* **pagination:** malformed cursor degrades to first page, not a 500 ([dca7356](https://github.com/mohamed-rekiba/arvel/commit/dca73566459bd15837ce85773eb79e52884e3934))
* **permission:** make role/permission middleware work with Arvel pipeline ([6d4bc36](https://github.com/mohamed-rekiba/arvel/commit/6d4bc36f37747a129b30166242b5f06dec358cf3))
* **permission:** match morph-alias discriminator in role/permission query helpers ([919ae7b](https://github.com/mohamed-rekiba/arvel/commit/919ae7bf838c64ccfd3d378349a455e4abdc3242))
* prevent mobile hero grid blowout on docs home page ([97f5581](https://github.com/mohamed-rekiba/arvel/commit/97f558108d13c8da905ae64c412564a129e06a7a))
* **quality:** mypy/pyright cleanup in maintenance + scheduling ([8bf3881](https://github.com/mohamed-rekiba/arvel/commit/8bf3881f624a7063a291685cec87f3949c0ac3a4))
* **queue,db:** address review nits — TEXT columns, AMQP startup leak, pin collector ([8070167](https://github.com/mohamed-rekiba/arvel/commit/80701670aa56fb1a04791aba92fe01ae6dc7c116))
* **queue,mail,notifications:** harden the queued-delivery rail (Laravel parity) ([e2d4fe4](https://github.com/mohamed-rekiba/arvel/commit/e2d4fe432921e22417b424d82eda57edeb3e6313))
* **queue:** give each job envelope a unique id ([5055cfb](https://github.com/mohamed-rekiba/arvel/commit/5055cfb7a2512085d0c4ea7f4550fc3d5a28c94e))
* **queue:** preserve FIFO within priority in redis driver ([12cbc6a](https://github.com/mohamed-rekiba/arvel/commit/12cbc6aa09e7a1642096c4ae1d2fa462130b5901))
* **queue:** reserve delayed jobs atomically so concurrent workers never double-release ([a59b6ac](https://github.com/mohamed-rekiba/arvel/commit/a59b6ac3755fcb7b3da4881b487c984a33be14ee))
* **queue:** reserve-then-ack so a worker crash redelivers the job ([e6bfa27](https://github.com/mohamed-rekiba/arvel/commit/e6bfa277ca94c2c92514220e081a839a74a60104))
* **queue:** scheduler after-hooks skip lost ticks + empty batch finalizes ([8d3445a](https://github.com/mohamed-rekiba/arvel/commit/8d3445ad8cc3819c3e800897290874c7c75bbee0))
* **queue:** store jobs epochs as BIGINT and index pop by priority ([122605d](https://github.com/mohamed-rekiba/arvel/commit/122605d0e8f2ad9ad11fa7bd9e90ad6911606f49))
* resolve linting issues ([f684832](https://github.com/mohamed-rekiba/arvel/commit/f68483241e08d3ab52b5f4f0be155181e2783227))
* resolve missing documentation issues ([dd9acfe](https://github.com/mohamed-rekiba/arvel/commit/dd9acfe87b2b26d3ce6be6f5d320fa05827d840d))
* resolve the formating issues ([5c42ee8](https://github.com/mohamed-rekiba/arvel/commit/5c42ee8b79dbc78625868b6d4269e99f6641b63e))
* **reverb:** correct presence channel protocol semantics ([67ac96c](https://github.com/mohamed-rekiba/arvel/commit/67ac96c399d8d614dd1fec27bfa1cfa0bec11917))
* **reverb:** wire the Redis broadcast→Reverb fan-out per ADR-013 §4 ([53c9371](https://github.com/mohamed-rekiba/arvel/commit/53c93713e4ef03554ef8d1b3dd3646a0b6b9e8bf))
* **review:** Date ordering returns NotImplemented for foreign types + doc nits ([2526e38](https://github.com/mohamed-rekiba/arvel/commit/2526e3879c1ee369bd2345a59b60983a27efad6c))
* **routing:** bind limiter in a provider so any boot resolves the full graph ([e0aa916](https://github.com/mohamed-rekiba/arvel/commit/e0aa9162a88c772db08fa91402c07ec8b05ad617))
* **routing:** drop redundant list[Any] cast that broke the mypy gate ([2e3bc61](https://github.com/mohamed-rekiba/arvel/commit/2e3bc61133aa67e17017c9d8452660927d51c11d))
* **routing:** hide __hidden__ on models nested in raw returns ([34fc1d2](https://github.com/mohamed-rekiba/arvel/commit/34fc1d272d23b5cd07f408e1a61ba6eff35fd724))
* **routing:** honour __hidden__ when a route returns a raw model ([7373003](https://github.com/mohamed-rekiba/arvel/commit/737300348a22c62647cb150308d596f212e6115d))
* **scaffold:** e2e migration count + scaffold token table's last_used_at ([b87b435](https://github.com/mohamed-rekiba/arvel/commit/b87b4354a3ecba06cba908cc03323cfe12e96778))
* **scheduler,maintenance:** error-tolerant ticks + maintenance except-paths ([5af2b5b](https://github.com/mohamed-rekiba/arvel/commit/5af2b5b36f6a7f5d73da1ab36312e3a93e3b61ee))
* **scheduling:** scope onOneServer election lock per minute ([ba1d911](https://github.com/mohamed-rekiba/arvel/commit/ba1d911aa07718a25287d40aba3ea14ab480abd8))
* **search:** guard filter field names + fail loud on queued-without-dispatcher ([512e738](https://github.com/mohamed-rekiba/arvel/commit/512e73889d846ab9d57e676b668fc3eecde8d579))
* **search:** render Meilisearch filters by value type ([f377ebc](https://github.com/mohamed-rekiba/arvel/commit/f377ebc8bd62cb77be04fa88a2caf007fb3d613e))
* **search:** restoring a soft-deleted searchable model re-indexes it ([a408cfb](https://github.com/mohamed-rekiba/arvel/commit/a408cfb0fc72b47f4fcbcba1607b34c7e5b7419a))
* **security:** allowlist gitleaks false positives from the scheduled full-history scan ([23f04ed](https://github.com/mohamed-rekiba/arvel/commit/23f04ed107253e766505e0ef2cb7ad980809b46f))
* **security:** crypto review fixes — corrupt-hash robustness on the auth path ([90ef712](https://github.com/mohamed-rekiba/arvel/commit/90ef712151cd852e5cd357a9b94700137b185ac0))
* **security:** resolve bandit findings at the source, not by skipping rules ([fdc87cf](https://github.com/mohamed-rekiba/arvel/commit/fdc87cfa6fe823a442e689af90c224b63a9a3c77))
* **security:** stop non-ASCII tokens from crashing constant-time guards into 500 ([af312aa](https://github.com/mohamed-rekiba/arvel/commit/af312aa9dcf7dc05661cf4a86e051d789be82f79))
* **session:** destroy the old store record on regenerate (WI-011) ([6c7233c](https://github.com/mohamed-rekiba/arvel/commit/6c7233c3a772ecda67d54587ffcae38d81492ccb))
* **session:** hash file-session id to block path traversal ([c13f28b](https://github.com/mohamed-rekiba/arvel/commit/c13f28b45653ee8bf0580da4f62a988906840dc5))
* **shell:** boot lazily so the REPL opens when the DB is down ([4538a40](https://github.com/mohamed-rekiba/arvel/commit/4538a4031f2352280803fbcba92f1122431585a5))
* **shell:** scope REPL boot to non-HTTP subsystems ([fe2e429](https://github.com/mohamed-rekiba/arvel/commit/fe2e429cb53311999b07f54dc5f7da60fdfbfa53))
* **skeleton:** map APP_KEY into config app.key ([f2f9603](https://github.com/mohamed-rekiba/arvel/commit/f2f9603ba61f66d75277b913a4bf757cf289d822))
* **skeleton:** move observability config skeleton out of workspace root ([ee1d5d5](https://github.com/mohamed-rekiba/arvel/commit/ee1d5d55a7e67414dc7fbb936310bc1e4e552ffc))
* **storefront:** remove dead "Specials" nav link ([8811f21](https://github.com/mohamed-rekiba/arvel/commit/8811f2108c3a1431a67dc28d991cbf99dcdf3d72))
* streamline code formatting and exception handling ([61d441f](https://github.com/mohamed-rekiba/arvel/commit/61d441f059dd332359505e8995cd6f859b857d0d))
* **support:** compare Collection intersect/diff by value ([eb08db4](https://github.com/mohamed-rekiba/arvel/commit/eb08db43c3102c0a4aa12da13cc527cc9c9eafbf))
* **support:** serialize datetime/Decimal/UUID/bytes in Collection.to_json ([adb72c0](https://github.com/mohamed-rekiba/arvel/commit/adb72c0b7a0116670a122fd4e461e502cba1d9eb))
* **support:** story-02 review follow-ups ([72bb711](https://github.com/mohamed-rekiba/arvel/commit/72bb711d3247f100d7621e63e07d56d3262db222))
* **testing:** story-11 review nits ([3da10e4](https://github.com/mohamed-rekiba/arvel/commit/3da10e414cd04fa9c929cb80719159c3c8636528))
* **tests:** simplify assertion for category slug in JSONB mapping test ([82ba34e](https://github.com/mohamed-rekiba/arvel/commit/82ba34e2777ae9e912c70660544a5f90927fdb83))
* **types:** annotate _build_served_asgi with concrete Application for serve_lifespan ([9c81d64](https://github.com/mohamed-rekiba/arvel/commit/9c81d64851f48fedead90f56e895b810d600c9f8))
* **types:** explicit re-export of current_user from http.request ([ab6e0cf](https://github.com/mohamed-rekiba/arvel/commit/ab6e0cf431025c5a76eb79aede3e4093cacfe01a))
* **validation:** actionable error for exists/unique without a DB session ([eeb073d](https://github.com/mohamed-rekiba/arvel/commit/eeb073dce4e415bdbb00978e6caa1f9cc16f05cd))


### Performance

* **ci:** parallelize test suites and unblock ecommerce-kit emulators ([152c2f5](https://github.com/mohamed-rekiba/arvel/commit/152c2f5630b5241b1b17d863c4d05ff6d7afd2bb))
* **ci:** speed up and align the integration test suites ([8766ca1](https://github.com/mohamed-rekiba/arvel/commit/8766ca108a49cdec1bdc946449f6b11afd1f1589))
* **console:** narrow boot for provider-only queue commands ([ae6f743](https://github.com/mohamed-rekiba/arvel/commit/ae6f74397fcefe190141aa23acf6f64614a60169))
* **image:** offload responsive Pillow work to a worker thread ([3530f3d](https://github.com/mohamed-rekiba/arvel/commit/3530f3d925c954cef185793f5da6ee9ab5720358))
* **permission:** batch role permission loading to kill N+1 ([3428f37](https://github.com/mohamed-rekiba/arvel/commit/3428f373c9b3b2ee41f56cb22f935b5ef59f7734))
* **test:** drop RabbitMQ management plugin from framework emulator ([ec5a934](https://github.com/mohamed-rekiba/arvel/commit/ec5a9342f62aec80d76b1f6a81004e1ed079f835))
* **test:** restore loadfile for kit emulator suite ([e98979b](https://github.com/mohamed-rekiba/arvel/commit/e98979be828456c6503542c48cd1bc3c2374c9fd))
* **test:** revert kit to per-worker emulator stacks ([eb8a460](https://github.com/mohamed-rekiba/arvel/commit/eb8a460c8268766abc50b766ebbaa46c5c82bfaa))
* **test:** seed ecommerce-kit catalog once via template DB ([69b2399](https://github.com/mohamed-rekiba/arvel/commit/69b239960ed5c394069c343c4dc2df35560aef2b))
* **test:** share one emulator stack across kit xdist workers ([78eb4c8](https://github.com/mohamed-rekiba/arvel/commit/78eb4c80e778fe69030430155302dbd41ab7d139))


### Refactors

* **arvent:** rename Eloquent → Arvent ([a84f9dc](https://github.com/mohamed-rekiba/arvel/commit/a84f9dc551617cd6f4f076baa03b4a8c8a31ef86))
* **auth:** read is_verified/is_suspended off Authenticatable ([4bbad8c](https://github.com/mohamed-rekiba/arvel/commit/4bbad8c77e394ad50c5cc7dc33373138e6bb89b8))
* **auth:** return Authenticatable from require_auth and Auth.user ([ed49b16](https://github.com/mohamed-rekiba/arvel/commit/ed49b1632294334eaf5face0b15a837927e1662d))
* **boundaries:** break auth&lt;-&gt;http cycle (unify current_user in support) ([77ab091](https://github.com/mohamed-rekiba/arvel/commit/77ab0914f369bf3fc4d7a6a6dc6f439479c8bd9a))
* **boundaries:** break cache&lt;-&gt;support cycle ([f4ea395](https://github.com/mohamed-rekiba/arvel/commit/f4ea395113e14dbbb04d4e20c89c7f4c26606349))
* **boundaries:** break http&lt;-&gt;pagination and pagination&lt;-&gt;views cycles ([e866405](https://github.com/mohamed-rekiba/arvel/commit/e8664051a41ee021f65dec438f8be649e22ee93f))
* **boundaries:** break http&lt;-&gt;telemetry cycle (prometheus split) ([eb43aa1](https://github.com/mohamed-rekiba/arvel/commit/eb43aa174a3b7dd94ce032ce61b0eda02b0a470e))
* **boundaries:** break kernel-&gt;telemetry and kernel-&gt;http cycles ([d1a2a9b](https://github.com/mohamed-rekiba/arvel/commit/d1a2a9b99998a7ab6f46b0b4f4fd9a60a3fa53ff))
* **boundaries:** drop eager telemetry-&gt;http middleware base ([bfecbc8](https://github.com/mohamed-rekiba/arvel/commit/bfecbc88f48adddd01b6f6b9d3aeddb80e5f337e))
* **config:** drop dead NoPrefix clause; document call() resolution limits ([206c810](https://github.com/mohamed-rekiba/arvel/commit/206c8102499a55ae5d31852c530ec956294598d4))
* **console:** drop unused args param from in-process command dispatch ([77a6342](https://github.com/mohamed-rekiba/arvel/commit/77a6342a51e89f2d8aeca0121f245d37786f3038))
* **console:** make arvel new kit-agnostic with per-kit finalize hook ([e27a522](https://github.com/mohamed-rekiba/arvel/commit/e27a522d52717b562605f0d58be189b78b99f989))
* **console:** promote exec_into and type test fakes for pyright ([a444640](https://github.com/mohamed-rekiba/arvel/commit/a444640e20051a3ade5e97d0d6a88c0a46b472cc))
* **database:** split Model god-object into mixins + full event lifecycle + casts + API Resources ([d3a93e0](https://github.com/mohamed-rekiba/arvel/commit/d3a93e0967d879282819a83bc4f91dc9d8091032))
* **deps:** replace httpx with httpx2 across all packages ([d462305](https://github.com/mohamed-rekiba/arvel/commit/d4623059f05f2bd750183844957426fdabc0b9a4))
* **ecommerce-kit:** adopt JsonResource for product/category responses ([173aed7](https://github.com/mohamed-rekiba/arvel/commit/173aed74841aff35bf423b16d8b309d8fcc4881d))
* **ecommerce-kit:** delete unused admin CRUD lib helpers ([d9dc800](https://github.com/mohamed-rekiba/arvel/commit/d9dc800df3a3550dd6314800455fcb8f508b3019))
* **ecommerce-kit:** delete unused cart/checkout lib helpers ([4810690](https://github.com/mohamed-rekiba/arvel/commit/48106904cad906eec45ec5979050096f301e8938))
* **ecommerce-kit:** drop dead admin list-fetch helpers ([dd1e196](https://github.com/mohamed-rekiba/arvel/commit/dd1e196401d2f8214f162c29d392a6ad5295d8ae))
* **ecommerce-kit:** drop test-driven storefront prefetch calls ([49a1d88](https://github.com/mohamed-rekiba/arvel/commit/49a1d88e49f035c53f38a24aafebd890eec6b96b))
* **ecommerce-kit:** move .env.example and pyproject into backend ([fbda8d0](https://github.com/mohamed-rekiba/arvel/commit/fbda8d0a1aa881daaef7e43922e6bf2e7f4c778c))
* **ecommerce:** centralize catalog visibility in a model scope ([906c8f7](https://github.com/mohamed-rekiba/arvel/commit/906c8f73d7ac0c58d523f4d10a503279d890fe02))
* **ecommerce:** delegate image-upload validation to arvel-image ([51a4581](https://github.com/mohamed-rekiba/arvel/commit/51a45813f520b74c2131a3934e95cea0dde8fb01))
* **ecommerce:** derive is_new and subtotal via model accessors ([6ae9b98](https://github.com/mohamed-rekiba/arvel/commit/6ae9b983f674ad0c711387e0f9125264f49fd3d3))
* **ecommerce:** make admin user detail fully Orval-driven ([48cc1fe](https://github.com/mohamed-rekiba/arvel/commit/48cc1fea599af59b212b058eac5d22d95bd39910))
* **ecommerce:** move tunables into the config layer ([716e47a](https://github.com/mohamed-rekiba/arvel/commit/716e47aff849226487005b348df837cdefdb7475))
* **ecommerce:** validate product FKs with framework Rule.exists ([cff2e84](https://github.com/mohamed-rekiba/arvel/commit/cff2e84de920855c88fbed7dc7472db5773f0552))
* **http:** declare global ASGI middleware like service providers ([a2df6b4](https://github.com/mohamed-rekiba/arvel/commit/a2df6b4b0becea9da6962312c08f824da1b4008f))
* improve code structure and performance across multiple modules ([12442c2](https://github.com/mohamed-rekiba/arvel/commit/12442c215c2f1df494c0d13c64cf7df1f29963bf))
* **ProductCard:** improve template structure and readability ([72e5db5](https://github.com/mohamed-rekiba/arvel/commit/72e5db505f7dfc23ee3bed3d94bba29f7dbc58ca))
* **queue,console:** failed-jobs ops live on QueueManager (G2 import boundary) ([b108c65](https://github.com/mohamed-rekiba/arvel/commit/b108c6542aa59be30d8daa7959df0d21209d5795))
* **queue:** QueueManager is now a Manager subclass ([3a9bb14](https://github.com/mohamed-rekiba/arvel/commit/3a9bb142309447f2c7557092d85cb28722ca3a25))


### Documentation

* **application:** document best-effort provider shutdown ([fd91687](https://github.com/mohamed-rekiba/arvel/commit/fd9168756a6fdef18e23af6af34457aa0593cffb))
* **cache:** correct database store description to app DB connection ([40c21ab](https://github.com/mohamed-rekiba/arvel/commit/40c21abb5bbda681fb13eb0fbed892f479986068))
* **changelog:** mark local file serving (STORAGE_LOCAL_SERVE) as landed ([0a15f22](https://github.com/mohamed-rekiba/arvel/commit/0a15f2207e132a4bb259fc1a15bf0cd5d1a701b6))
* **changelog:** triage bucket-3 feature gaps against the codebase ([ab36157](https://github.com/mohamed-rekiba/arvel/commit/ab36157d084ca6daeae6703a230e83ad18b87174))
* **cli:** enrich CLI reference with workflows and custom commands ([17dd9fc](https://github.com/mohamed-rekiba/arvel/commit/17dd9fc2cecdf1461f05e6df8bb68307f6789bad))
* **client:** clarify retry(when=) exhaustion + blanket-fake stray semantics ([99bdfc0](https://github.com/mohamed-rekiba/arvel/commit/99bdfc073195784ae5e89da338d49eb69110385a))
* **console:** list the new commands (migrate:fresh/refresh, db:wipe, cache:clear, key:generate, storage:link, make:enum/exception/test) ([6da52b1](https://github.com/mohamed-rekiba/arvel/commit/6da52b1d74fc25531f9cb52a1e0642d20a5d7f54))
* **core-concepts:** add quick-start sections across lifecycle docs ([5bcd8e0](https://github.com/mohamed-rekiba/arvel/commit/5bcd8e059e34c09f8b94afea4fcb8574d14ce15f))
* drop comparison references across code and docs ([23f49e5](https://github.com/mohamed-rekiba/arvel/commit/23f49e590b06d22eff7f06e9bb71679f57abb9c3))
* **error-handling:** correct ProblemDetailsHandler catch-all note ([4462c76](https://github.com/mohamed-rekiba/arvel/commit/4462c7680d20dcdd5be328f854087dc49ecaff05))
* **features:** enrich feature docs with quick-start workflows ([84cde6b](https://github.com/mohamed-rekiba/arvel/commit/84cde6bd62839a91e488328c55978cec81cc567b))
* fix accuracy drift across guides, features, and packages ([85608bc](https://github.com/mohamed-rekiba/arvel/commit/85608bc89741dfaa88800943bf9cf391a64ed7f7))
* **frontend:** add SPA integration quick-start workflow ([9ce56ef](https://github.com/mohamed-rekiba/arvel/commit/9ce56ef0e46c846672b4f41ab0e8467e5b9886ba))
* **getting-started:** add quick-start paths for install and structure ([e833903](https://github.com/mohamed-rekiba/arvel/commit/e83390368d20f25d522585e9504a30f2276c1eed))
* **kits:** add ecommerce kit quick-start commands ([37c78a8](https://github.com/mohamed-rekiba/arvel/commit/37c78a87e72a166dde539a6532acd38737e7066d))
* make the docs consistent with the merged observability features ([a20bdcc](https://github.com/mohamed-rekiba/arvel/commit/a20bdcc1f19543d7fc921b1e24895521af8ec6ba))
* **middleware:** document the declarative global middleware stack ([4f13f76](https://github.com/mohamed-rekiba/arvel/commit/4f13f7610025f700d78ee831ccaf212c7e3133fb))
* **orm:** enhance query builder documentation with local and global scopes examples ([da39175](https://github.com/mohamed-rekiba/arvel/commit/da3917555478556e819b95d1615713ba3e7f773b))
* **orm:** rewrite ORM site docs with richer examples ([24dc043](https://github.com/mohamed-rekiba/arvel/commit/24dc043471d11d2ee2369847d7136459c33228e2))
* **packages:** rewrite companion package docs with richer examples ([955390e](https://github.com/mohamed-rekiba/arvel/commit/955390e9bdf1177f8c51d255f978018d85159361))
* **reference:** add API reference navigation quick-start ([8ce959a](https://github.com/mohamed-rekiba/arvel/commit/8ce959adf9ce5e0c14558b962570ae2a5a02eb32))
* **scheduling:** correct stale note — kernel honors maintenance/outputTo ([01eecec](https://github.com/mohamed-rekiba/arvel/commit/01eececcabb3e6ee8075664ecf487d834fdd8bef))
* **session:** fix stale StartSession example to use SessionCookie/SameSite ([7bcb9a2](https://github.com/mohamed-rekiba/arvel/commit/7bcb9a2665943ec77d79adbf5e86b01039558546))
* **site:** add section hubs, doc map, and cross-links ([97055a1](https://github.com/mohamed-rekiba/arvel/commit/97055a1f1b414d207aca0de67e1654fc463f6d26))
* **spatie:** remove third-party Spatie references ([bf2d682](https://github.com/mohamed-rekiba/arvel/commit/bf2d6824bd23d3c4d6e33dbf08e398ee90795f14))
* sync docs with the features added this round ([c4e29da](https://github.com/mohamed-rekiba/arvel/commit/c4e29dae014e452f39bba73928afa3d916c37e63))
* sync lifecycle, session, and container docs with hardening ([0f2d3b8](https://github.com/mohamed-rekiba/arvel/commit/0f2d3b802a0bd3b27879638975b2a0c1585c0e4c))
* **telemetry:** add a hands-on "new to observability" tour with real output ([09c9ad7](https://github.com/mohamed-rekiba/arvel/commit/09c9ad7c97d54672f6315867f886fb3a67dd5861))
* testing.md integration tier, migrations.md default string length. ([f898c42](https://github.com/mohamed-rekiba/arvel/commit/f898c42340e6601c0d19c58e4559f11d4189075f))
* **the-basics:** add quick-start sections across HTTP fundamentals ([0925510](https://github.com/mohamed-rekiba/arvel/commit/0925510bd8284346b84d752a932d4b66a7eac348))
* **type-safety:** clarify usage of Literal, Enum, and str for closed value sets ([326dd7d](https://github.com/mohamed-rekiba/arvel/commit/326dd7df27a395c4277998f2658ec58bd8a95bb7))
* **validation:** note FormRequest structural-before-semantic divergence ([1aa9303](https://github.com/mohamed-rekiba/arvel/commit/1aa930363fcacee969f5fadf08bb5835ab3bb798))

## [0.52.1](https://github.com/mohamed-rekiba/arvel/compare/v0.52.0...v0.52.1) (2026-07-05)


### Bug Fixes

* atomic decrement for batch counters to stop lost decrements ([c764232](https://github.com/mohamed-rekiba/arvel/commit/c76423280dcccb5eaca65d178cc0a4512982d334))

## [0.52.0](https://github.com/mohamed-rekiba/arvel/compare/v0.51.0...v0.52.0) (2026-07-05)


### Features

* **auth:** policy discovery + Gate guest-deny + Sanctum completeness + Fortify 2FA ([8b2c7fd](https://github.com/mohamed-rekiba/arvel/commit/8b2c7fda0a7968038a1c3fa7d40b2d37e8556a4b))
* **auth:** session login security + single-use password-reset broker + email-hash verification ([4de7c41](https://github.com/mohamed-rekiba/arvel/commit/4de7c4149ba97ee3d7b4aac6e3325be9ea8e01ad))
* **broadcasting,mail,notifications:** channels+auth, multipart/markdown mail, notification broadcast ([4508a65](https://github.com/mohamed-rekiba/arvel/commit/4508a65b5ae195f6b0820d2167cf2ba39edc7fe0))
* **cache:** full verb set + owner-tokened locks + tags + Redis facade ([d50d6b0](https://github.com/mohamed-rekiba/arvel/commit/d50d6b0d5576c62e72e75b678bc5c7475393ec02))
* **client:** HTTP-client parity — builders, response wrapper, pool, fake ([a9ed3bc](https://github.com/mohamed-rekiba/arvel/commit/a9ed3bc91c6655b9e5268ac1e176477313c575ed))
* **console:** A8 scaffold-name fix + I/O, prompts, signature grammar, Artisan.call, maintenance, stub:publish ([3a96de9](https://github.com/mohamed-rekiba/arvel/commit/3a96de9754bd79cfd928d70b4013eed1cb46f54d))
* **database:** EloquentCollection, QB breadth, dialect upsert + diff sync, cursor pagination ([45ce2b8](https://github.com/mohamed-rekiba/arvel/commit/45ce2b8b94986c32b86f79548832cbd6271ef673))
* **database:** schema evolution + seeder controls + relationship factories ([71ec98a](https://github.com/mohamed-rekiba/arvel/commit/71ec98a63f13cd4d5da306fc65a39c3b713cf80b))
* **db,http,client:** add builder/accessor capabilities the proof-app needed ([fb3b711](https://github.com/mohamed-rekiba/arvel/commit/fb3b711c78cbc8f46dd47e42b74d7f35ed1d0327))
* **features:** Pennant-style feature flags (array/database/cache drivers) ([1dcab2f](https://github.com/mohamed-rekiba/arvel/commit/1dcab2fbe0fce23b3d89049d15087ebb7a17cda5))
* **filesystem:** full Storage surface + visibility + fake ([dc5acf8](https://github.com/mohamed-rekiba/arvel/commit/dc5acf8075a66e6d880f691732d3917b8bcde439))
* **http:** fluent responses/redirects/cookies, url helpers, CSRF except, controller middleware, typed seams ([da1c220](https://github.com/mohamed-rekiba/arvel/commit/da1c2203e9d1a24e548058c93ff9298f77f761b9))
* **http:** RateLimiter + named throttle limiters with rate-limit headers ([e13f75e](https://github.com/mohamed-rekiba/arvel/commit/e13f75e7cfc74ce05279018e28eaebbe2c105f4f))
* **kernel:** -parity exception handler lifecycle ([d461df6](https://github.com/mohamed-rekiba/arvel/commit/d461df64c5693322d5c3e9c62c667db61e321214))
* **queue:** batching + unique jobs + job middleware + scheduler hardening (A3) ([1901aa0](https://github.com/mohamed-rekiba/arvel/commit/1901aa006505da793bc8a6ffc13871daaff77b1b))
* **queue:** reliability — sequential chains, queued listeners, retry-release, visibility, timeout, worker flags, Context ([11afc42](https://github.com/mohamed-rekiba/arvel/commit/11afc425a26811a5b2653f76bcf6705cf40827d9))
* **search:** Scout-parity fluent builder, queued-indexing seam, scout CLI ([058f315](https://github.com/mohamed-rekiba/arvel/commit/058f315df8ecd6d5bc6c117ca0609ae5ee4f2ea7))
* **security:** hash driver manager + AES-256-GCM serialize-aware Encrypter ([d23d729](https://github.com/mohamed-rekiba/arvel/commit/d23d7293c71cca23f490660ce847b265c7812d4c))
* **support:** Pipeline, Context, Process, Concurrency + Collection parity ops ([c6b464d](https://github.com/mohamed-rekiba/arvel/commit/c6b464d4a1e0a4c3ed03c47e662f9884a8143118))
* **testing:** notification/bus/http fakes + response assertions + artisan() helper ([d204d2d](https://github.com/mohamed-rekiba/arvel/commit/d204d2de2e916043eebd40792d42443659633c38))
* **validation:** A7 url/email fixes + ~35 new rules + FormRequest rules() bridge ([6832e84](https://github.com/mohamed-rekiba/arvel/commit/6832e8495acc3a45eb90e026fb0adceb328eda9d))


### Bug Fixes

* **auth:** login drops a stale _impersonator_id (defence in depth) ([f44b6e8](https://github.com/mohamed-rekiba/arvel/commit/f44b6e821064eaff41d481d1953e44c03c8dcbfd))
* **auth:** reset access-token per request + bind 2FA challenge to pending user ([fffa098](https://github.com/mohamed-rekiba/arvel/commit/fffa098e604ae05f7d0f74dd3f9ce372a29c56f0))
* **broadcasting,mail:** story-19 hardening nits ([a278bf2](https://github.com/mohamed-rekiba/arvel/commit/a278bf2f161e88bad4d6012fc800bebc55189411))
* **cache:** story-06 review nits ([751e9a1](https://github.com/mohamed-rekiba/arvel/commit/751e9a1e17de95dcd77d6119693230db3e502432))
* **console:** constant-time maintenance secret + Artisan.call works from a running loop ([6abe6e9](https://github.com/mohamed-rekiba/arvel/commit/6abe6e961bdc3f7dc4e808486b82d0c1b86e3a61))
* **database:** story-10 review nits ([69d4398](https://github.com/mohamed-rekiba/arvel/commit/69d439807a6f4b20340f57c9a48b5aa0c1d51cd0))
* **database:** to_dict/to_json unwraps collection/object/stringable/decimal casts ([b2bfe2c](https://github.com/mohamed-rekiba/arvel/commit/b2bfe2c46065ad89d18e8b96eb1c8bdedcd31826))
* **filesystem:** contain path traversal — reject ../ escaping the disk root ([219e2f8](https://github.com/mohamed-rekiba/arvel/commit/219e2f8a18ee4a93166bfc83071d98c989bc7d72))
* **http:** __Host- cookie forces Secure (prefix invariant) ([0c8ce3c](https://github.com/mohamed-rekiba/arvel/commit/0c8ce3c83b36ceddb2adf688d40a509aad0d7793))
* **kernel:** exception-handler review follow-ups ([68a5d42](https://github.com/mohamed-rekiba/arvel/commit/68a5d42872e285127b534e3e3c18145349a80c50))
* **pagination:** malformed cursor degrades to first page, not a 500 ([dca7356](https://github.com/mohamed-rekiba/arvel/commit/dca73566459bd15837ce85773eb79e52884e3934))
* **queue:** scheduler after-hooks skip lost ticks + empty batch finalizes ([8d3445a](https://github.com/mohamed-rekiba/arvel/commit/8d3445ad8cc3819c3e800897290874c7c75bbee0))
* **routing:** bind limiter in a provider so any boot resolves the full graph ([e0aa916](https://github.com/mohamed-rekiba/arvel/commit/e0aa9162a88c772db08fa91402c07ec8b05ad617))
* **scaffold:** e2e migration count + scaffold token table's last_used_at ([b87b435](https://github.com/mohamed-rekiba/arvel/commit/b87b4354a3ecba06cba908cc03323cfe12e96778))
* **search:** guard filter field names + fail loud on queued-without-dispatcher ([512e738](https://github.com/mohamed-rekiba/arvel/commit/512e73889d846ab9d57e676b668fc3eecde8d579))
* **security:** crypto review fixes — corrupt-hash robustness on the auth path ([90ef712](https://github.com/mohamed-rekiba/arvel/commit/90ef712151cd852e5cd357a9b94700137b185ac0))
* **security:** resolve bandit findings at the source, not by skipping rules ([fdc87cf](https://github.com/mohamed-rekiba/arvel/commit/fdc87cfa6fe823a442e689af90c224b63a9a3c77))
* **support:** story-02 review follow-ups ([72bb711](https://github.com/mohamed-rekiba/arvel/commit/72bb711d3247f100d7621e63e07d56d3262db222))
* **testing:** story-11 review nits ([3da10e4](https://github.com/mohamed-rekiba/arvel/commit/3da10e414cd04fa9c929cb80719159c3c8636528))


### Refactors

* **database:** split Model god-object into mixins + full event lifecycle + casts + API Resources ([d3a93e0](https://github.com/mohamed-rekiba/arvel/commit/d3a93e0967d879282819a83bc4f91dc9d8091032))


### Documentation

* **client:** clarify retry(when=) exhaustion + blanket-fake stray semantics ([99bdfc0](https://github.com/mohamed-rekiba/arvel/commit/99bdfc073195784ae5e89da338d49eb69110385a))
* drop comparison references across code and docs ([23f49e5](https://github.com/mohamed-rekiba/arvel/commit/23f49e590b06d22eff7f06e9bb71679f57abb9c3))
* **validation:** note FormRequest structural-before-semantic divergence ([1aa9303](https://github.com/mohamed-rekiba/arvel/commit/1aa930363fcacee969f5fadf08bb5835ab3bb798))

## [0.51.0](https://github.com/mohamed-rekiba/arvel/compare/v0.50.0...v0.51.0) (2026-07-04)


### Features

* **http:** Redis-backed session store via session.driver config ([0fef79e](https://github.com/mohamed-rekiba/arvel/commit/0fef79e0a3ae3598df9e427c80f5d3a80e3d4892))
* **kernel:** with_public_dir/with_lang_dir app-bootstrap overrides ([95d0c82](https://github.com/mohamed-rekiba/arvel/commit/95d0c82a4e8a8b89a5c1d82b9e6f16df6a6b8933))
* **routing:** Router.public() — Laravel-parity public/ web root + SPA fallback ([70a9629](https://github.com/mohamed-rekiba/arvel/commit/70a96295ce64f6980664e128ba688afbf2290360))


### Bug Fixes

* **security:** allowlist gitleaks false positives from the scheduled full-history scan ([23f04ed](https://github.com/mohamed-rekiba/arvel/commit/23f04ed107253e766505e0ef2cb7ad980809b46f))

## [0.50.0](https://github.com/mohamed-rekiba/arvel/compare/v0.49.0...v0.50.0) (2026-07-03)


### Features

* **database:** where() gains the 'ilike' operator ([125b557](https://github.com/mohamed-rekiba/arvel/commit/125b557566c20b2c816bf096f68cc27f0afc25bd))


### Bug Fixes

* **database:** raw-select datetime hydration parses SQLite string values ([7d54cca](https://github.com/mohamed-rekiba/arvel/commit/7d54cca3e0ed5493d0be314828b1c34497a905a6))
* **search:** restoring a soft-deleted searchable model re-indexes it ([a408cfb](https://github.com/mohamed-rekiba/arvel/commit/a408cfb0fc72b47f4fcbcba1607b34c7e5b7419a))

## [0.49.0](https://github.com/mohamed-rekiba/arvel/compare/v0.48.0...v0.49.0) (2026-07-02)


### Features

* **application:** add metrics route if metrics are enabled ([eed83cb](https://github.com/mohamed-rekiba/arvel/commit/eed83cb6882a8dae9c7fe1bf57e6860d3c9ebb32))
* **application:** add support for custom .env file path and enhance JWT secret validation ([65fc33f](https://github.com/mohamed-rekiba/arvel/commit/65fc33f56a25fd382ccd98e5851b621d46bd65d1))
* **arvel-image:** responsive images, manipulations, and package audit hardening ([5b39980](https://github.com/mohamed-rekiba/arvel/commit/5b3998034086495d7d4728d6a45e9a57b6b905f7))
* **arvel:** port LogManager + harden Container, Session, and Auth ([bf41e56](https://github.com/mohamed-rekiba/arvel/commit/bf41e565f8b07cf58565f7504a29ef294025cb03))
* **arvon:** add fluent datetime layer over whenever ([e204e81](https://github.com/mohamed-rekiba/arvel/commit/e204e81067ed9fab1aa5c1d29f5ec62913f05621))
* **auth:** HasRoles.remove_role — revoke a role (Spatie removeRole parity) ([733510c](https://github.com/mohamed-rekiba/arvel/commit/733510ca99490445eef8f56a94d6e57124c8ecc6))
* **auth:** permission guards accept a list with all/any semantics ([6ed283e](https://github.com/mohamed-rekiba/arvel/commit/6ed283eb93d9ad5b26560fe0a9cef9c46dd45e68))
* **auth:** revoke access tokens and share the login throttle ([c27ce83](https://github.com/mohamed-rekiba/arvel/commit/c27ce83eb3fe167d498449dfd86fd66293113bc8))
* **auth:** Role.permissions() — a role's granted permissions (Spatie parity) ([95cfada](https://github.com/mohamed-rekiba/arvel/commit/95cfada89cca35f1e463fb9ea454da8457ed5135))
* **boundaries:** enforce the module DAG via import-linter layers (empty allowlist) ([162f360](https://github.com/mohamed-rekiba/arvel/commit/162f3603deadd93f8d55479336935a28ca1ae3b8))
* **cli:** add db pre-flight checks and ecommerce-kit healthcheck ([6083146](https://github.com/mohamed-rekiba/arvel/commit/6083146108308396efb1de5942897d4ba6bdbfc4))
* **cli:** auto re-exec global arvel into project .venv ([8332713](https://github.com/mohamed-rekiba/arvel/commit/8332713185f9a741caf31b4974ac54d93d2cac8a))
* **client:** Client.timeout() chainable (parity with base_url/with_headers) ([709f470](https://github.com/mohamed-rekiba/arvel/commit/709f470a12a417c8c0d875413cf2c7cada077fff))
* **cli:** fetch ecommerce kit from github release ([6713a29](https://github.com/mohamed-rekiba/arvel/commit/6713a29583f9bc2f7cd11649eed6a7ef539d68c5))
* **cli:** fetch ecommerce kit from github release ([e251f04](https://github.com/mohamed-rekiba/arvel/commit/e251f045b4cda571a0cbf82cb58f68ae428c2c33))
* **cli:** lazy --help listing and in-project command dispatch ([d725912](https://github.com/mohamed-rekiba/arvel/commit/d7259128520c2d3abe7482052a16098601ea06b2))
* **cli:** needs-based subsystem bootstrap ([82aa7fa](https://github.com/mohamed-rekiba/arvel/commit/82aa7fac6c39eed99a54a0dd1a2083f8d0be5454))
* **cli:** print kit-specific next steps after arvel new ([f48e739](https://github.com/mohamed-rekiba/arvel/commit/f48e7398ab1cacb9f27531b9b80794d031a312ae))
* **cli:** show boot spinner during framework startup ([94b6351](https://github.com/mohamed-rekiba/arvel/commit/94b63518f7ff1347091352dbd224f2cff3f661c7))
* **config,storage:** config-file cascade and storage:link static serving ([d2ae2d5](https://github.com/mohamed-rekiba/arvel/commit/d2ae2d5a006b0e1b7326daf4d9531caa3b89ea52))
* **console:** add missing Laravel commands (migrate:fresh/refresh, db:wipe, cache:clear, key:generate, storage:link, make:enum/exception/test) ([3014f09](https://github.com/mohamed-rekiba/arvel/commit/3014f09a518195ed575cbbba8a13ab4d3e5d6059))
* **console:** make:event, make:listener, make:cast generators ([e26beac](https://github.com/mohamed-rekiba/arvel/commit/e26beacb8bd257b244891c48e70106b15033bf72))
* **console:** openapi:export — render the OpenAPI document to a file ([52191e1](https://github.com/mohamed-rekiba/arvel/commit/52191e19f4cb1fb61953f9f618327428450767c7))
* **console:** plain ASCII banner on bare `arvel`, no color ([755fcba](https://github.com/mohamed-rekiba/arvel/commit/755fcba2f0de8a2e78061dfc0f1ed5a1957e496b))
* **console:** unify programmatic dispatch through Typer ([42e5979](https://github.com/mohamed-rekiba/arvel/commit/42e5979624cc2d8729526c4949d582f2f9d58129))
* **database:** model observers + fix queued binary attachments over a real broker ([6ec8e7d](https://github.com/mohamed-rekiba/arvel/commit/6ec8e7d0f99547296a76164c8cc21cc8fbbbc7e1))
* **database:** Schema.table + drop_column (Laravel Schema::table); server-side defaults ([0ad3146](https://github.com/mohamed-rekiba/arvel/commit/0ad31465872e2b78f58c56ab7245b181fb2834c3))
* **database:** store datetimes as real DateTime values, not ISO strings (DR-0023) ([c15c846](https://github.com/mohamed-rekiba/arvel/commit/c15c84682e27bf041f4d744d8d80c5c6f66715e2))
* **dates:** Date instances order naturally (Carbon parity) ([cd32372](https://github.com/mohamed-rekiba/arvel/commit/cd32372f949683788189ceda26a030b36391504a))
* **docs:** restructure documentation with new architecture and lifecycle files ([c18ed3c](https://github.com/mohamed-rekiba/arvel/commit/c18ed3c9cd2315cf2f3d22434840909862c56b97))
* **ecommerce-kit:** add Windows healthcheck script and OS-aware make target ([ee662eb](https://github.com/mohamed-rekiba/arvel/commit/ee662ebcc732aa5638e973f4d3c49995749e9de2))
* **ecommerce-kit:** aggregate admin dashboard stats at the DB ([2c46f51](https://github.com/mohamed-rekiba/arvel/commit/2c46f5162c0b1dc8b337b8e38de06777011b3195))
* **ecommerce-kit:** cosmic hero and storefront animation layer ([ff6c317](https://github.com/mohamed-rekiba/arvel/commit/ff6c317e8e47c946f5c5c8d3aa5e1bd3199a3d8f))
* **ecommerce-kit:** customer-role listener, cart stock lock, checkout guard ([f7b2b01](https://github.com/mohamed-rekiba/arvel/commit/f7b2b01dec57feebba7182166287212b12b48c5b))
* **ecommerce-kit:** persist the storefront wishlist for guests ([183430b](https://github.com/mohamed-rekiba/arvel/commit/183430b6cbd9b07127ac6acdf3dd511c1c082509))
* **ecommerce-kit:** use full arvel-image feature set E2E ([39e58f0](https://github.com/mohamed-rekiba/arvel/commit/39e58f0db3d4c04874bcee14509a7dca4a6b8e44))
* **ecommerce:** add suspend/reinstate controls to admin user detail ([573de13](https://github.com/mohamed-rekiba/arvel/commit/573de133b5b2a5d1bb91843c98d22232fbb2a682))
* **ecommerce:** derive is_new from created_at instead of hardcoding false ([f450cc7](https://github.com/mohamed-rekiba/arvel/commit/f450cc71770eb86f43d1a4dcb1abda20581bb3c2))
* **ecommerce:** give product cards soft resting elevation ([0bb73fa](https://github.com/mohamed-rekiba/arvel/commit/0bb73fa7cfce653cd64d5ddc3588080ea34b4cd5))
* **ecommerce:** refresh design foundation — display font + soft elevation ([56ad1d0](https://github.com/mohamed-rekiba/arvel/commit/56ad1d07ea87bd458310978086d074d009878bab))
* **ecommerce:** seed sample orders so best-sellers has data ([2243901](https://github.com/mohamed-rekiba/arvel/commit/22439014ef8babd4b575498259952bf09665c939))
* **ecommerce:** storefront filter searches the full catalog ([133863f](https://github.com/mohamed-rekiba/arvel/commit/133863f24a66e7125baa5492785b286efc7137e3))
* **extras:** add an 'oidc' optional-dependency extra (pyjwt[crypto]) ([14396bb](https://github.com/mohamed-rekiba/arvel/commit/14396bbc98dd0f1be4fe58c276291d36c44faf3a))
* **foundation:** harden container/app/console and wire the token guard ([5a76889](https://github.com/mohamed-rekiba/arvel/commit/5a768895899bf38daac57cf1bad34b20022495a1))
* **http:** add Http facade and Http.fake outbound client ([097098f](https://github.com/mohamed-rekiba/arvel/commit/097098f00183f8d15dc26a1762c14baf79e2ef85))
* **http:** add response() and redirect() helpers ([2cdf841](https://github.com/mohamed-rekiba/arvel/commit/2cdf841826b11ae4face016b282d919def72056a))
* **http:** consolidate CSRF middlewares and accept more token sources ([57d84a9](https://github.com/mohamed-rekiba/arvel/commit/57d84a9876e59421b8147530226d2bd9d678f1a2))
* **http:** HTML form method-spoofing (Laravel [@method](https://github.com/method)) ([81b1a1f](https://github.com/mohamed-rekiba/arvel/commit/81b1a1fce9021e09f5e0025715183792be1878f9))
* **http:** trust proxies on the general request path ([e6b0d90](https://github.com/mohamed-rekiba/arvel/commit/e6b0d901e022edbc604a0ecc831f9818d313414b))
* **http:** typed query parameters — injected + documented in OpenAPI ([34b82d2](https://github.com/mohamed-rekiba/arvel/commit/34b82d2a3678e9880abf5f9e16af42c4c00bc5e2))
* **i18n:** translatable model attributes (HasTranslations + Translatable cast) ([777276d](https://github.com/mohamed-rekiba/arvel/commit/777276deb97d8da269abebf59c8d34ff81ac7be2))
* **i18n:** translatable model attributes (HasTranslations + Translatable cast) ([392ab7c](https://github.com/mohamed-rekiba/arvel/commit/392ab7ca716d824137cd2b1aa7d550ab4160dcd4))
* **image,orm:** DX-first media API with strict eager-load morph descriptors ([666134c](https://github.com/mohamed-rekiba/arvel/commit/666134cf8742c0e0327c3412f8d727184ef1556e))
* **kit:** multiple product images on detail page ([2eded9f](https://github.com/mohamed-rekiba/arvel/commit/2eded9f495342aaf401ca7dc9ac06d591cdc0313))
* **kits:** ship ecommerce kit as a github release download ([8ff904e](https://github.com/mohamed-rekiba/arvel/commit/8ff904e0d96f873e1fd1cea877af23f616ae9d67))
* **mail:** app-wide default sender (config mail.from) — Laravel parity ([e96587d](https://github.com/mohamed-rekiba/arvel/commit/e96587dab88673230fff8ca6291332a94747b9f2))
* **media:** HasMedia.delete_media — remove ONE item (row + stored files) ([b8a69e2](https://github.com/mohamed-rekiba/arvel/commit/b8a69e2d07f7d2daf1d09cf3072f3a1f2a52fb2a))
* multipart [@method](https://github.com/method), per-app manager config, richer reference app ([d7e29c4](https://github.com/mohamed-rekiba/arvel/commit/d7e29c4cbf7a8672e2b6d0f26fc27498990f428a))
* **openapi:** OpenID Connect security scheme (.secure("oidc")) ([30bbd72](https://github.com/mohamed-rekiba/arvel/commit/30bbd72d716ca566c80982ade72f8263b156ac6e))
* **orm,http:** Laravel-parity relation serialization + conditional clauses ([7ae5798](https://github.com/mohamed-rekiba/arvel/commit/7ae57988fbc4f48bfd12cf4322ba1537f80f02fc))
* **orm,http:** ModelNotFound renders as 404 + export migration Schema type ([29a479a](https://github.com/mohamed-rekiba/arvel/commit/29a479a2b32916d70a824ba590d190d9e7229677))
* **orm,image:** model-level morph class override; media via framework eager loading ([c2ae2d4](https://github.com/mohamed-rekiba/arvel/commit/c2ae2d411b275132b9a1c8387b6c0542ccc1b303))
* **orm:** complete QueryMixin parity and use model query shortcuts ([2f3ebbc](https://github.com/mohamed-rekiba/arvel/commit/2f3ebbc0a118878726d0b1d8888023671d4fd4a5))
* **orm:** enhance eager loading to respect soft delete scopes ([8a9aae8](https://github.com/mohamed-rekiba/arvel/commit/8a9aae87a6c6ccf2ea76a2b204699e3396b48cb7))
* **orm:** per-operation autocommit for Laravel transaction parity ([d750b98](https://github.com/mohamed-rekiba/arvel/commit/d750b9898186c03374902b95d4ec785b57153350))
* **orm:** typed classmethod query entry-points (Model.where/with_/order_by/...) ([ac735d4](https://github.com/mohamed-rekiba/arvel/commit/ac735d47fcbf4da196fd021253b708686d82e850))
* **orm:** where_in accepts a subquery (Laravel whereIn(col, $subquery)) ([79a1276](https://github.com/mohamed-rekiba/arvel/commit/79a12765b94dbe2ea83056f6dc5b1d4abb6c20ae))
* **orm:** where_json_like — LIKE against a value inside a JSON column ([bdd5d06](https://github.com/mohamed-rekiba/arvel/commit/bdd5d0678fcc048d439eeccc046914b57fdcdb87))
* **orm:** where_raw + where_exists (Laravel whereRaw / whereExists) ([013e73e](https://github.com/mohamed-rekiba/arvel/commit/013e73e5a7a6a135b207518df3df453ded311089))
* **pagination:** Laravel-parity paginators (paginate/simple_paginate, links(), JSON) ([2ff86f2](https://github.com/mohamed-rekiba/arvel/commit/2ff86f24e6a30a3febd24df4db360f7affac4fbb))
* **routing:** per-route response status override (Route.post(...).status(200)) ([9f0e903](https://github.com/mohamed-rekiba/arvel/commit/9f0e90346f001ece44dda6244d8d5b813a5c1a78))
* **routing:** signed-URL key defaults to app key + ValidateSignature (signed) middleware ([d447141](https://github.com/mohamed-rekiba/arvel/commit/d447141fb810df601e5f72f5466888974c51b989))
* **scaffold:** ship cache/filesystems/mail config files (Laravel parity + discoverability) ([e77f04e](https://github.com/mohamed-rekiba/arvel/commit/e77f04e7cbd8e611f04b8abdd5a3f76b850d464a))
* **schema:** t.btree_index — composite + expression indexes (jsonb per-locale lookups) ([3e541e4](https://github.com/mohamed-rekiba/arvel/commit/3e541e4e1e9c8d6aba8b0a7c3cdb7a898bdf857a))
* **schema:** warn + degrade Postgres-only DDL on other dialects ([4161e18](https://github.com/mohamed-rekiba/arvel/commit/4161e18c1505f8b8e2c33c6874d54b81f171e737))
* **search:** Searchable.make_all_searchable + remove_all_from_search (Scout parity) ([eff2dd6](https://github.com/mohamed-rekiba/arvel/commit/eff2dd6be92fba37dd360f63022283ebb616f29e))
* **session:** honor SESSION_SECURE/SESSION_SAME_SITE and add typed enums ([b4173ce](https://github.com/mohamed-rekiba/arvel/commit/b4173ce216e1103dc619375e67bf996cd9064321))
* **storage:** implement AzureDriver.temporary_url via SAS token ([591313d](https://github.com/mohamed-rekiba/arvel/commit/591313d53e663d70568fb803df0734e5201950a7))
* **storage:** serve local-disk files at the framework ([ae11338](https://github.com/mohamed-rekiba/arvel/commit/ae113380426a22b14c7de55819c949bf00ed9682))
* **telemetry:** auto-instrument cache + outbound HTTP, and propagate traces to queue jobs ([07a835f](https://github.com/mohamed-rekiba/arvel/commit/07a835f169551af7ba0bb1f3c2c5d549f0d816d4))
* **telemetry:** auto-instrument database queries with OpenTelemetry CLIENT spans ([41e65d4](https://github.com/mohamed-rekiba/arvel/commit/41e65d496ac5c1a549550fb697e87480c4de9ca3))
* **telemetry:** auto-instrument HTTP requests with OpenTelemetry server spans ([28a8a1a](https://github.com/mohamed-rekiba/arvel/commit/28a8a1ae45505176041ff9623990385ffcae94b7))
* **telemetry:** export metrics and logs alongside traces (full OTLP signal set) ([e7adf38](https://github.com/mohamed-rekiba/arvel/commit/e7adf3853e2c34d9dbe34b7e81915c3e23f8d96c))
* **telemetry:** OpenTelemetry tracing wired from config, backend-agnostic via OTLP ([538efae](https://github.com/mohamed-rekiba/arvel/commit/538efae1d7021dbe9106c1c43f0d47025411d34c))
* **telemetry:** record HTTP request metrics (count + duration) in the middleware ([c73bdbb](https://github.com/mohamed-rekiba/arvel/commit/c73bdbb26d5e61e7f2396c1de73650bd572d2488))
* **testing:** bus/notification fakes + refresh_database + json helpers ([021677b](https://github.com/mohamed-rekiba/arvel/commit/021677b1f51dc722529b0ff75f60e523519fdbfb))
* **testing:** reset_rate_limiter/reset_sessions for test isolation ([5503547](https://github.com/mohamed-rekiba/arvel/commit/55035475ce11182e12427622160d67db5aa963a7))
* **validation:** add bail, conditional presence, date rules, custom rules, Rule builders ([f06f8d0](https://github.com/mohamed-rekiba/arvel/commit/f06f8d05e44edb117d53b47217a38d9b886ea68f))
* **validation:** support nested and wildcard field paths ([9fe866a](https://github.com/mohamed-rekiba/arvel/commit/9fe866afb5cf58d3f44871356e463155fd85613e))
* **views:** auth()/guest() template globals (Laravel @auth/[@guest](https://github.com/guest)) ([0858d2b](https://github.com/mohamed-rekiba/arvel/commit/0858d2bddcda84c86f1d8ec267bcc6b6a697e2ed))


### Bug Fixes

* **application:** drain every provider on shutdown even when one fails ([275382a](https://github.com/mohamed-rekiba/arvel/commit/275382a06e97d65941604d7c0f52fd33b0af8669))
* **application:** widen Application.make to match Container.make signature ([11c5036](https://github.com/mohamed-rekiba/arvel/commit/11c5036bb918f8296e184c5ff2d17f109f883219))
* **arvel-image:** close three post-F5 gaps in responsive images and EXIF ([b7e9ef3](https://github.com/mohamed-rekiba/arvel/commit/b7e9ef36e4cf99494dc478c22b484a0e0a56115a))
* **arvel-image:** close two post-gap edge cases in responsive images ([512fdea](https://github.com/mohamed-rekiba/arvel/commit/512fdeac7cc00b427c1a788f40e7cacc9d7c3d84))
* **arvel-image:** make process_one runner/gen args optional ([538e3e7](https://github.com/mohamed-rekiba/arvel/commit/538e3e7c2cdd319854e5e243c21e29b7bfc2268c))
* **arvel:** correct SyslogChannel handler type under mypy platform pruning ([6a94438](https://github.com/mohamed-rekiba/arvel/commit/6a94438caf22a0845cc48604f36d620582d8a261))
* **arvel:** harden container extend, session guard, cookie expiry, and session lifecycle ([bf466d4](https://github.com/mohamed-rekiba/arvel/commit/bf466d48d11730e4dc9cd47214340db25c00789a))
* **arvel:** inject resend rate-limit store into AuthController ([d244aaf](https://github.com/mohamed-rekiba/arvel/commit/d244aaf26622884984d145deee322aa6473a12d5))
* **audit:** close partial-boot leaks and session/container edge cases ([aa09830](https://github.com/mohamed-rekiba/arvel/commit/aa09830a9eb6972219499e930f8faf885bfc1ee3))
* **audit:** harden container, auth, session, and console boot ([d53bcef](https://github.com/mohamed-rekiba/arvel/commit/d53bcef05d8e3d2b9476715c43835dc95d363a88))
* **audit:** harden lifecycle, container, sessions, and CLI failure modes ([d447ddd](https://github.com/mohamed-rekiba/arvel/commit/d447ddd4a9486310377761a031b4aaaf83e61b9c))
* **audit:** read provider-bound AuditConfig instead of reloading .env per write ([6012528](https://github.com/mohamed-rekiba/arvel/commit/6012528fb76a166d3c5b05932aca83ee9cafd2d5))
* **auth,session:** harden guards, gate, CSRF, and session lifecycle ([5d6f405](https://github.com/mohamed-rekiba/arvel/commit/5d6f4056532bc7aaf028b8443766c33a804989cb))
* **auth:** align password_resets storage name across migration, model, and CLI ([a9aa1c6](https://github.com/mohamed-rekiba/arvel/commit/a9aa1c62eef7a2d2c7d5768d59461d076aaa4e53))
* **auth:** detect refresh-token reuse and revoke the family ([f682950](https://github.com/mohamed-rekiba/arvel/commit/f68295076ca6c9a1745dc706b2ea63d456f2e6b3))
* **auth:** ensure boolean return for post ownership check in PostPolicy ([be42e80](https://github.com/mohamed-rekiba/arvel/commit/be42e8063b03f686e78234aefd20cc7d70e17169))
* **auth:** keep "database" as the canonical provider driver string ([f7f5d85](https://github.com/mohamed-rekiba/arvel/commit/f7f5d855339799956c850749ce42d5da56865f30))
* **auth:** resolve AuthController per request, not at boot ([ff466e7](https://github.com/mohamed-rekiba/arvel/commit/ff466e7bd630a1fd2f4c1adc3a7e6b6e4baf714b))
* **auth:** return 403 for an unverified logged-in user, not 401 ([b1660f9](https://github.com/mohamed-rekiba/arvel/commit/b1660f974f1f23645ddd9a60e6a73bad7454dbc5))
* **auth:** run policy before() filters in the Gate ([0d74dd3](https://github.com/mohamed-rekiba/arvel/commit/0d74dd37ea93dee08c886ced0576b9ac9ffc6f96))
* bind loopback in serve importability test ([acbb35e](https://github.com/mohamed-rekiba/arvel/commit/acbb35ea26682829ee33f36bc629b15a78e6524e))
* **boundaries:** maintenance resolves cache itself (http-&gt;cache legal) ([d4a4326](https://github.com/mohamed-rekiba/arvel/commit/d4a4326dfce8cd3c82ca306f9429867b904ba615))
* **broadcasting:** make the default broadcast payload JSON-safe (WI-012) ([08ff45b](https://github.com/mohamed-rekiba/arvel/commit/08ff45b45d4860b8896e47ba5fa166069f273c35))
* **cache:** a dead Redis raises instead of silently no-oping ([94e7b8c](https://github.com/mohamed-rekiba/arvel/commit/94e7b8c55cae6a27f0dbde04647259fc36f47291))
* **cache:** anchor RateLimiter window to the first hit, not the last ([94b5c02](https://github.com/mohamed-rekiba/arvel/commit/94b5c022e695e03d116eab678f4a06b3f022cc65))
* **cache:** drop stale ttl arg from CacheConfig calls ([dcdba51](https://github.com/mohamed-rekiba/arvel/commit/dcdba51ad019736c7f55e5d64351f0b2db93b651))
* **cache:** redis put(ttl=None) stores forever, drop CACHE_TTL default ([11ad567](https://github.com/mohamed-rekiba/arvel/commit/11ad567b5c5d0f3c27b4e7c1aad6d1af03c3e715))
* **ci/gitleaks:** allowlist valkey image-tag entropy + repair renamed-test path ([e8c40e8](https://github.com/mohamed-rekiba/arvel/commit/e8c40e8536d9e5d60a112161fe393f234437d33a))
* **ci:** pin kit emulator tests to one xdist worker ([ae7e9a6](https://github.com/mohamed-rekiba/arvel/commit/ae7e9a6bbff6d0815330afa7641825ace6d45ac3))
* **cli:** re-exec into project venv and silence shell route logs ([8aac184](https://github.com/mohamed-rekiba/arvel/commit/8aac1843d38c6268bf532abaa9ddb89096964165))
* **config:** make dotted dict lookups key-only ([16790c6](https://github.com/mohamed-rekiba/arvel/commit/16790c6fc71c4d60c0d61d1412f1459046fe843b))
* **console:** --help shows the Laravel colon command names (not hyphenated) ([da14e1b](https://github.com/mohamed-rekiba/arvel/commit/da14e1b13de7de4af24bd0621ee78cac225d4107))
* **console:** annotate venv re-exec nosec suppressions with rationale ([15a340e](https://github.com/mohamed-rekiba/arvel/commit/15a340e9baeae77cdf11b39a3aa100bfea6ffa6e))
* **console:** arvel down/up boot the project app ([d56d387](https://github.com/mohamed-rekiba/arvel/commit/d56d38708ef4ca5bfd68cfaab71966051997e675))
* **console:** run async CLI commands on the single event loop ([f30e4d5](https://github.com/mohamed-rekiba/arvel/commit/f30e4d585977e6a327bf29959bdd543f2015061f))
* **console:** run scaffolded compose uv sync from backend/ ([69017d7](https://github.com/mohamed-rekiba/arvel/commit/69017d7da655337111253b19a08b5acd648c8b9f))
* **console:** run uv sync in the kit's python project dir ([2d6fcdb](https://github.com/mohamed-rekiba/arvel/commit/2d6fcdbc21087ba93d6eaad5bce09e623df45aa1))
* **container:** resolve async bindings at any depth in amake ([a2c74ae](https://github.com/mohamed-rekiba/arvel/commit/a2c74ae72cdb3ea0371921c6b95441f3f23e9a20))
* **context:** round-trip hidden data through dehydrate/hydrate ([b355298](https://github.com/mohamed-rekiba/arvel/commit/b355298ddb8ed4e98d325c8e68bd6b47a47ac7f5))
* **database:** bind json key in where_json_path to prevent SQL injection ([364b656](https://github.com/mohamed-rekiba/arvel/commit/364b6568881dff1c0c740160beb295ecdea4a88d))
* **database:** fire retrieved on all read paths; load_missing detects async relations ([9a188c2](https://github.com/mohamed-rekiba/arvel/commit/9a188c2d5d7137f7737557aea2c164005d5c9277))
* **database:** PG column-type fidelity for UUID PKs and json casts ([93d2741](https://github.com/mohamed-rekiba/arvel/commit/93d27418b758458ac13c4b43015b3367e1196b79))
* **database:** run seeder after-commit callbacks once rows are committed ([534e0aa](https://github.com/mohamed-rekiba/arvel/commit/534e0aaa76e72ab9fa3c8741f62269c28a86a2cb))
* **database:** store datetimes as UTC so SQLite round-trips keep the instant (review B1) ([3d52898](https://github.com/mohamed-rekiba/arvel/commit/3d52898bba6dc3f5faf8b05965c8447b20a01208))
* **database:** use dialect-aware JsonB/TsVector in column helpers ([356446e](https://github.com/mohamed-rekiba/arvel/commit/356446ef5b0d787cf6970524723db63cf57c1e33))
* **database:** wrap seeders in a database transaction for improved consistency ([b64085e](https://github.com/mohamed-rekiba/arvel/commit/b64085e879635fc8885cb3aabaefab206bc1bfe3))
* disable testcontainers ryuk reaper and document CLI scaffold ([de607fd](https://github.com/mohamed-rekiba/arvel/commit/de607fd58c26fca91e96c00111ac521b0a4f93b0))
* **docs:** update link for getting started section in index page ([fb7e4fc](https://github.com/mohamed-rekiba/arvel/commit/fb7e4fc747fa4202f7def34f47df9ba55eed78fc))
* **docs:** update module description for clarity and accuracy ([4d532b7](https://github.com/mohamed-rekiba/arvel/commit/4d532b72bbd2bb55701562a484729851dbf371f7))
* **ecommerce-kit/frontend:** stop cart re-render, link product, upgrade orval to 8 ([8b20c64](https://github.com/mohamed-rekiba/arvel/commit/8b20c64668a2380c0eae2a41b5d49882ae4f0180))
* **ecommerce-kit:** 404 on cart PATCH/DELETE for unknown item ([a436600](https://github.com/mohamed-rekiba/arvel/commit/a4366005abf621b2b8b9b4e099f55ceb9731b239))
* **ecommerce-kit:** checkout self-loads the cart on mount ([535845a](https://github.com/mohamed-rekiba/arvel/commit/535845a4048b602dc39b227c6b82d571b52b680a))
* **ecommerce-kit:** fix broken self-service registration flow ([d80dc48](https://github.com/mohamed-rekiba/arvel/commit/d80dc4827bf52d1b741962b83fcbfd4134c23d3b))
* **ecommerce-kit:** gate catalog edit/restore on the update permission ([75e3ee8](https://github.com/mohamed-rekiba/arvel/commit/75e3ee882433f6a0de2ffdfd397b799768125b71))
* **ecommerce-kit:** gate force-delete on role level, not just permission ([8d2f80d](https://github.com/mohamed-rekiba/arvel/commit/8d2f80d5a8c314ca030cb4067eb5d5a1ca8f9c9f))
* **ecommerce-kit:** guard the /admin catch-all route ([6c1d076](https://github.com/mohamed-rekiba/arvel/commit/6c1d076b8aa96eb1c633183e833e3219b50f39e9))
* **ecommerce-kit:** harden admin self-delete and category parent_id validation ([13c0131](https://github.com/mohamed-rekiba/arvel/commit/13c01319feaa020b6839e06ecd4176f09f44340a))
* **ecommerce-kit:** hydrate auth store on guard and unify admin-access check ([b9daf0a](https://github.com/mohamed-rekiba/arvel/commit/b9daf0a25ef0f076ed4321f81eeaba9591c5d74b))
* **ecommerce-kit:** localize admin date/currency formatting ([e9d1338](https://github.com/mohamed-rekiba/arvel/commit/e9d1338f84d2fc59423441ff7f7bc0471b301a84))
* **ecommerce-kit:** localize checkout estimated-delivery date ([c80dfee](https://github.com/mohamed-rekiba/arvel/commit/c80dfee777bd7ca3dca474b25e75d0124cacde1d))
* **ecommerce-kit:** localize storefront listing and search copy ([fcca2f8](https://github.com/mohamed-rekiba/arvel/commit/fcca2f8a5c8efcf8ee430ac7282fdd34cebebcb3))
* **ecommerce-kit:** make seed refresh the catalog view unconditionally ([63bdb05](https://github.com/mohamed-rekiba/arvel/commit/63bdb05a55a32106a2950a42fceb9d6dc94fe4a7))
* **ecommerce-kit:** only confirm an order the account owner placed ([1e524a6](https://github.com/mohamed-rekiba/arvel/commit/1e524a6e86e2c3116b54c688dde6b1fa65b0db78))
* **ecommerce-kit:** order data integrity after force-delete and on checkout totals ([4fceaa4](https://github.com/mohamed-rekiba/arvel/commit/4fceaa4f7f3ce7ba9ab87274dd567434ee3def2c))
* **ecommerce-kit:** point feature-test cache at testcontainer Redis ([caea13e](https://github.com/mohamed-rekiba/arvel/commit/caea13eb086b104736608d3ad7ebf1d78b0618ba))
* **ecommerce-kit:** point integration tests at testcontainers MinIO ([faafe81](https://github.com/mohamed-rekiba/arvel/commit/faafe8111c2f29f8ce8d0f500b740f7087763a89))
* **ecommerce-kit:** refresh client RBAC on admin navigation ([ca5a753](https://github.com/mohamed-rekiba/arvel/commit/ca5a7535da27a7f588cb81b56b8a737da1d0e93d))
* **ecommerce-kit:** reject category self-parent and parent cycles ([5e65461](https://github.com/mohamed-rekiba/arvel/commit/5e65461ab5ba2e57149df888db1db4e6d1f341d2))
* **ecommerce-kit:** return 404 for admin PATCH on missing product ([8a39d1e](https://github.com/mohamed-rekiba/arvel/commit/8a39d1ee8089dae5e479177a3d7f7a060d165961))
* **ecommerce-kit:** route expired admin sessions to the admin login ([35015dd](https://github.com/mohamed-rekiba/arvel/commit/35015dd11405f88a2dd03c1f229fc856b8856569))
* **ecommerce-kit:** serialize concurrent checkout to prevent duplicate orders ([f2b15ef](https://github.com/mohamed-rekiba/arvel/commit/f2b15ef97100da5dc4af964279d08fbb3e31a712))
* **ecommerce-kit:** show effective permissions on the admin user detail ([40c793f](https://github.com/mohamed-rekiba/arvel/commit/40c793f7c17946ea7a07983e0cb74a985d3571da))
* **ecommerce-kit:** smooth storefront hover and reveal motion ([de03ad1](https://github.com/mohamed-rekiba/arvel/commit/de03ad1c5e704d0666267d923bb8628ab4ceacaa))
* **ecommerce-kit:** snapshot order line names in shopper locale ([be7249e](https://github.com/mohamed-rekiba/arvel/commit/be7249e7ae72196543683de8f195c4e8066f521b))
* **ecommerce-kit:** type and validate the checkout shipping address ([fbdc10c](https://github.com/mohamed-rekiba/arvel/commit/fbdc10c664d51d1ed4d4acfc5f471a62d0a7fc1b))
* **ecommerce-kit:** use os.urandom noise in _make_jpeg so responsive srcset is non-empty ([c93394a](https://github.com/mohamed-rekiba/arvel/commit/c93394abe1712c8d363cd0f15d0431cf3ae59654))
* **ecommerce-kit:** validate product price/stock bounds and malformed cart ids ([de5917b](https://github.com/mohamed-rekiba/arvel/commit/de5917b78b78eb55d0d80d75368a3488adbd664f))
* **ecommerce/api:** clamp page size on all list endpoints ([75c9ac8](https://github.com/mohamed-rekiba/arvel/commit/75c9ac8dc8d50bd6fc0f3bcd9115cdc2c455c871))
* **ecommerce/auth:** block post-login open redirect ([d02dd04](https://github.com/mohamed-rekiba/arvel/commit/d02dd040c613c9f273c5ded85e5efc96fd13d07f))
* **ecommerce/orders:** bound customer order history pagination ([6aa13e3](https://github.com/mohamed-rekiba/arvel/commit/6aa13e3cb59bc7cf7f3d644b5848fbd58d5e9e3c))
* **ecommerce:** bound and sniff product media uploads ([1a2e415](https://github.com/mohamed-rekiba/arvel/commit/1a2e4156822c651cfdf7344b7ba7cee51217b6ef))
* **ecommerce:** cap product media upload size to prevent memory DoS ([e638ae9](https://github.com/mohamed-rekiba/arvel/commit/e638ae9ec66a4b80e2991c5c7a0280c80e74b7e5))
* **ecommerce:** catalog status enum, cart re-snapshot, force-delete gate ([f946e7a](https://github.com/mohamed-rekiba/arvel/commit/f946e7a581951f31001be7cd1b92a7bc7c28e779))
* **ecommerce:** coalesce catalog refresh so writes aren't dropped ([4c34a24](https://github.com/mohamed-rekiba/arvel/commit/4c34a24a720094ebb1708565fbe5d9c98761a181))
* **ecommerce:** deny-by-default the test seed/refresh endpoints ([d374182](https://github.com/mohamed-rekiba/arvel/commit/d37418235c7121fbfebe6abb085b983a2f1f912a))
* **ecommerce:** drop fabricated dashboard trends and flash-sale discounts ([4d798bc](https://github.com/mohamed-rekiba/arvel/commit/4d798bc74ae7c883750d7db94cd8dc58ecd44536))
* **ecommerce:** drop fabricated discount claims from storefront promos ([587dc24](https://github.com/mohamed-rekiba/arvel/commit/587dc24ba6220d64d1ca6afcecc88625092fa4af))
* **ecommerce:** exclude cancelled orders from dashboard revenue ([8f9df85](https://github.com/mohamed-rekiba/arvel/commit/8f9df85226787edc1ef16311fe21212aefe70610))
* **ecommerce:** extend A01 outrank guard to role/permission mutators ([4185a8a](https://github.com/mohamed-rekiba/arvel/commit/4185a8a45b4d78d2a6969e782708b31cd471a0c1))
* **ecommerce:** gate admin routes by per-feature permission ([3d8feb6](https://github.com/mohamed-rekiba/arvel/commit/3d8feb6b66827fc3b6c4ad18d253d73a63194711))
* **ecommerce:** graceful force-delete with dependent orders ([a46237f](https://github.com/mohamed-rekiba/arvel/commit/a46237f50ccbc0c40342c7c30f3cbfcd36ca3192))
* **ecommerce:** guard admin user lifecycle against privilege escalation ([71df4a7](https://github.com/mohamed-rekiba/arvel/commit/71df4a776797cf4f48597c0c7737fc896d17e9bf))
* **ecommerce:** honor defaultTab so /register opens the register tab ([af40810](https://github.com/mohamed-rekiba/arvel/commit/af40810a20ce8b4c31e6e57e688c1df409c0175a))
* **ecommerce:** improve code formatting and readability ([86fa75c](https://github.com/mohamed-rekiba/arvel/commit/86fa75c429357c5ed3f0d5bc9570dafcf3a340c9))
* **ecommerce:** lock order row on cancel to prevent double stock restore ([8009d9c](https://github.com/mohamed-rekiba/arvel/commit/8009d9c6b78152e8e725d08483d066bc3c5058d2))
* **ecommerce:** manual catalog refresh never reports product_count -1 ([3ad34c1](https://github.com/mohamed-rekiba/arvel/commit/3ad34c1deff74bf3d1a98925d364c2141931b045))
* **ecommerce:** pass placed order id to the account success banner ([ff490f8](https://github.com/mohamed-rekiba/arvel/commit/ff490f8741973820472441d2fab3b68290c3a343))
* **ecommerce:** re-snapshot cart price on quantity PATCH ([7773d5d](https://github.com/mohamed-rekiba/arvel/commit/7773d5d368bee39b8919d7e3c02502570d0aad9f))
* **ecommerce:** reject malformed pagination cursor with 422 ([3b1dfd0](https://github.com/mohamed-rekiba/arvel/commit/3b1dfd05459a7a44722ab170288440b7408c9248))
* **ecommerce:** render real role-permission grants in admin matrix ([e0c55d4](https://github.com/mohamed-rekiba/arvel/commit/e0c55d4e68c9f5726cb624859a6a4bfaf64d30cc))
* **ecommerce:** repair admin contracts and drop fabricated UI data ([7267369](https://github.com/mohamed-rekiba/arvel/commit/7267369f7e0f457e14cb25cd847d3fc3fd55e643))
* **ecommerce:** replace fabricated hero claims with honest copy ([4d2145b](https://github.com/mohamed-rekiba/arvel/commit/4d2145be05405af7d61540eb237a000cee79514c))
* **ecommerce:** report unavailable cart items distinctly from low stock ([e772bc5](https://github.com/mohamed-rekiba/arvel/commit/e772bc58687a4b977afeef733854635f488932e6))
* **ecommerce:** require both view grants for translations endpoint ([3d37e11](https://github.com/mohamed-rekiba/arvel/commit/3d37e11b24dcbea1cf8a287051ec334c033547df))
* **ecommerce:** return 404 when deleting an unknown admin resource ([be57be7](https://github.com/mohamed-rekiba/arvel/commit/be57be7e7c7bd4775ce86e36b3fccb9ae27363a3))
* **ecommerce:** return 409 when force-deleting referenced category/vendor ([5bfa265](https://github.com/mohamed-rekiba/arvel/commit/5bfa26580f5b241aee004b575ef94557f1c07cec))
* **ecommerce:** route cart store error fallbacks through i18n ([8e9b0be](https://github.com/mohamed-rekiba/arvel/commit/8e9b0be250cbd1fc1118e9ba5c007714ea8ac960))
* **ecommerce:** scope storefront search to active category, gate short queries ([ea33fbb](https://github.com/mohamed-rekiba/arvel/commit/ea33fbb13e61adaf79ef3c2c9ce4935e93603386))
* **ecommerce:** show charged snapshot prices in the cart, not live ones ([95458fe](https://github.com/mohamed-rekiba/arvel/commit/95458fe36ea5686ea442535f0f25acbcf529969e))
* **ecommerce:** surface unavailable cart lines instead of ghosts ([77272f1](https://github.com/mohamed-rekiba/arvel/commit/77272f102b8d85999b145f071f65657d18db16c1))
* **ecommerce:** update environment configuration for Docker setup ([6333da9](https://github.com/mohamed-rekiba/arvel/commit/6333da95769edd356b9df42f2a732225fa72af0c))
* **ecommerce:** validate product category/vendor FK at the API ([19a2ac3](https://github.com/mohamed-rekiba/arvel/commit/19a2ac39b816c7ebb43baeae0cd8ab10e8ebf43d))
* **ecommerce:** widen users.name to 255 to match register contract ([cd64546](https://github.com/mohamed-rekiba/arvel/commit/cd6454658f21d9eff3dc8d08346db176f16d587d))
* **encryption:** raise DecryptionError on malformed base64 payloads ([d91a1e6](https://github.com/mohamed-rekiba/arvel/commit/d91a1e6d6d2332070695e61ce8093a9172c9dc0a))
* **events:** log queued-listener enqueue failures instead of running inline ([3a15670](https://github.com/mohamed-rekiba/arvel/commit/3a15670e2c42bdfaf6179d20c2348df8285b72da))
* format code for better readability in telemetry processing functions ([b8ea2dc](https://github.com/mohamed-rekiba/arvel/commit/b8ea2dc2daea5d731729e2e561da7abc899a31ca))
* **foundation:** harden config, container, CLI paths, and scheduler signals ([d3c9de1](https://github.com/mohamed-rekiba/arvel/commit/d3c9de121843dc99d7e3bb64a4bdfad256f69f47))
* **framework:** module-by-module audit hardening (WI-001..010) ([6404515](https://github.com/mohamed-rekiba/arvel/commit/64045152e2135cf1f95bcaa5aaf9e5be190a5710))
* **hashing:** make Hash.check and needs_rehash algorithm-aware ([645b79a](https://github.com/mohamed-rekiba/arvel/commit/645b79a06e4186adb681159e1938dc54c22aacd2))
* **http:** builder global middleware actually runs on the served app ([551e08e](https://github.com/mohamed-rekiba/arvel/commit/551e08e3f9efa86de02d8e0f678980b7e4c0f55b))
* **http:** map malformed pagination cursor to 400, not 500 ([ffca562](https://github.com/mohamed-rekiba/arvel/commit/ffca562e1cfd0f23d8f335d4e893114cf36a7786))
* **http:** render RFC 7807 problem+json for unhandled errors ([0f162f0](https://github.com/mohamed-rekiba/arvel/commit/0f162f0eaff4c3d4ab24e0a86369a11f939e5d13))
* **http:** run after-commit callbacks after the session is unbound ([4b79e21](https://github.com/mohamed-rekiba/arvel/commit/4b79e21f21399dfbe91ea7344e9271a56975be9d))
* **i18n:** block path traversal in translation loaders ([3af8385](https://github.com/mohamed-rekiba/arvel/commit/3af83851700592d8f0b2f7dbc13eed841fd7b88a))
* **i18n:** select plural form by locale rule, not raw count ([6ef824c](https://github.com/mohamed-rekiba/arvel/commit/6ef824c4ff188872b4c7b6033d43b2b5d0105e3f))
* **i18n:** set_translation stores a dict, not a double-encoded string (review finding) ([d152d9c](https://github.com/mohamed-rekiba/arvel/commit/d152d9c2af7ba1aefca54c58db7aab0db887ee4a))
* **i18n:** Translatable.set returns a dict (JSON column serializes once) ([31b082c](https://github.com/mohamed-rekiba/arvel/commit/31b082c4e253b6cd16b601d5e5faec370739a09c))
* **image:** enforce decompression-bomb guard and add set_max_pixels ([ce57fc4](https://github.com/mohamed-rekiba/arvel/commit/ce57fc4bf4f69e73db0dc72654d4f2f03933c3f4))
* **kit/services:** remove hard-coded conversion lists and dead seeder fallback ([9a8cd78](https://github.com/mohamed-rekiba/arvel/commit/9a8cd7833a6169ff75d5a03f91fcf01352c0fbbd))
* **kits:** localize ecommerce docker-compose for scaffolded projects ([8124b6a](https://github.com/mohamed-rekiba/arvel/commit/8124b6a5cb85182e161f68e697395fbbcd709a0e))
* **kits:** route unauthenticated admin visitors to admin login ([0c811d0](https://github.com/mohamed-rekiba/arvel/commit/0c811d0809c963b671bda8182c743c97baa240c1))
* **kits:** unbreak ecommerce kit dependency resolution ([80f2a24](https://github.com/mohamed-rekiba/arvel/commit/80f2a245d0785ed6f86b6efdeef4d0e37c620fbf))
* **logging:** redact secret log fields by substring ([31586d3](https://github.com/mohamed-rekiba/arvel/commit/31586d301dd3767d32a4f01b6de1bf05a72297b8))
* **logging:** redact secrets nested in dicts/lists, not just top-level keys ([7dace93](https://github.com/mohamed-rekiba/arvel/commit/7dace939962b06c06b0243a5b88d4f197eb8b2a2))
* **mail,notifications:** queued mailables/notifications survive a real broker ([da9c9de](https://github.com/mohamed-rekiba/arvel/commit/da9c9de18b4d0448b5a8463e909d5ba2fa3f29af))
* **mail:** apply global mail.from and render from_name ([347306b](https://github.com/mohamed-rekiba/arvel/commit/347306b85dc16b95ad08cdf3797eef183a9d16e8))
* **media:** convert to RGB before a JPEG conversion (alpha can't be encoded) ([5af20af](https://github.com/mohamed-rekiba/arvel/commit/5af20afc694dc5c8a5ab4e0d15508c2abbcc7a92))
* **migrate:** drop_all drops views/materialized views first (Postgres) ([d65c3cf](https://github.com/mohamed-rekiba/arvel/commit/d65c3cf569ae9083558cc8076228c502d40026b6))
* **migrate:** idempotent migrations + concise CLI errors (no traceback wall) ([80035f8](https://github.com/mohamed-rekiba/arvel/commit/80035f8a05b422d73b8bcdda2101c226c51d5e5a))
* **migrations:** pre-flight DB check in migrate:fresh/refresh ([eb92dfc](https://github.com/mohamed-rekiba/arvel/commit/eb92dfc66a856dc2fb0be454cd8ab4be883c434c))
* **oauth:** default Microsoft email_verified to false when claim absent ([b99d837](https://github.com/mohamed-rekiba/arvel/commit/b99d837d0f4225465c71afa22a59f4e1b577065a))
* **observability:** stop X-Forwarded-For from bypassing /_health and /_metrics CIDR guards ([9a5ad2d](https://github.com/mohamed-rekiba/arvel/commit/9a5ad2d0c01b36ba854d0110601e9ebe62f5bfe6))
* **openapi:** handler docstring becomes the operation description ([8770daf](https://github.com/mohamed-rekiba/arvel/commit/8770daf1a3342197f07a8f522ca974cc36f08e83))
* **orm:** accept Laravel string forms in Model.where/or_where ([f5282dc](https://github.com/mohamed-rekiba/arvel/commit/f5282dcf6053f9cb47a4150ecdf6ec65cf4d4066))
* **orm:** timestamps on by default (Laravel parity) + datetime-safe json cast ([a92c7d8](https://github.com/mohamed-rekiba/arvel/commit/a92c7d8f5f128e3d0b01234bc40ed171d35738cd))
* **orm:** update query syntax for model retrieval to match Laravel style ([aa4429c](https://github.com/mohamed-rekiba/arvel/commit/aa4429c9a097a24c4392c3ab5ebe88d16d680b64))
* **pagination:** address review nits (per_page&gt;=1 guard, list query params, real e2e date proof) ([ce7df61](https://github.com/mohamed-rekiba/arvel/commit/ce7df6123d3751bdba5407332836540343456924))
* **permission:** make role/permission middleware work with Arvel pipeline ([6d4bc36](https://github.com/mohamed-rekiba/arvel/commit/6d4bc36f37747a129b30166242b5f06dec358cf3))
* **permission:** match morph-alias discriminator in role/permission query helpers ([919ae7b](https://github.com/mohamed-rekiba/arvel/commit/919ae7bf838c64ccfd3d378349a455e4abdc3242))
* prevent mobile hero grid blowout on docs home page ([97f5581](https://github.com/mohamed-rekiba/arvel/commit/97f558108d13c8da905ae64c412564a129e06a7a))
* **quality:** mypy/pyright cleanup in maintenance + scheduling ([8bf3881](https://github.com/mohamed-rekiba/arvel/commit/8bf3881f624a7063a291685cec87f3949c0ac3a4))
* **queue,db:** address review nits — TEXT columns, AMQP startup leak, pin collector ([8070167](https://github.com/mohamed-rekiba/arvel/commit/80701670aa56fb1a04791aba92fe01ae6dc7c116))
* **queue,mail,notifications:** harden the queued-delivery rail (Laravel parity) ([e2d4fe4](https://github.com/mohamed-rekiba/arvel/commit/e2d4fe432921e22417b424d82eda57edeb3e6313))
* **queue:** give each job envelope a unique id ([5055cfb](https://github.com/mohamed-rekiba/arvel/commit/5055cfb7a2512085d0c4ea7f4550fc3d5a28c94e))
* **queue:** preserve FIFO within priority in redis driver ([12cbc6a](https://github.com/mohamed-rekiba/arvel/commit/12cbc6aa09e7a1642096c4ae1d2fa462130b5901))
* **queue:** reserve delayed jobs atomically so concurrent workers never double-release ([a59b6ac](https://github.com/mohamed-rekiba/arvel/commit/a59b6ac3755fcb7b3da4881b487c984a33be14ee))
* **queue:** reserve-then-ack so a worker crash redelivers the job ([e6bfa27](https://github.com/mohamed-rekiba/arvel/commit/e6bfa277ca94c2c92514220e081a839a74a60104))
* **queue:** store jobs epochs as BIGINT and index pop by priority ([122605d](https://github.com/mohamed-rekiba/arvel/commit/122605d0e8f2ad9ad11fa7bd9e90ad6911606f49))
* resolve linting issues ([f684832](https://github.com/mohamed-rekiba/arvel/commit/f68483241e08d3ab52b5f4f0be155181e2783227))
* resolve missing documentation issues ([dd9acfe](https://github.com/mohamed-rekiba/arvel/commit/dd9acfe87b2b26d3ce6be6f5d320fa05827d840d))
* resolve test issues and remove outdated RTMs ([3a440a4](https://github.com/mohamed-rekiba/arvel/commit/3a440a40a5d299af66b5764171dbebc9adf985b0))
* resolve the formating issues ([5c42ee8](https://github.com/mohamed-rekiba/arvel/commit/5c42ee8b79dbc78625868b6d4269e99f6641b63e))
* **reverb:** correct presence channel protocol semantics ([67ac96c](https://github.com/mohamed-rekiba/arvel/commit/67ac96c399d8d614dd1fec27bfa1cfa0bec11917))
* **reverb:** wire the Redis broadcast→Reverb fan-out per ADR-013 §4 ([53c9371](https://github.com/mohamed-rekiba/arvel/commit/53c93713e4ef03554ef8d1b3dd3646a0b6b9e8bf))
* **review:** Date ordering returns NotImplemented for foreign types + doc nits ([2526e38](https://github.com/mohamed-rekiba/arvel/commit/2526e3879c1ee369bd2345a59b60983a27efad6c))
* **routing:** drop redundant list[Any] cast that broke the mypy gate ([2e3bc61](https://github.com/mohamed-rekiba/arvel/commit/2e3bc61133aa67e17017c9d8452660927d51c11d))
* **routing:** hide __hidden__ on models nested in raw returns ([34fc1d2](https://github.com/mohamed-rekiba/arvel/commit/34fc1d272d23b5cd07f408e1a61ba6eff35fd724))
* **routing:** honour __hidden__ when a route returns a raw model ([7373003](https://github.com/mohamed-rekiba/arvel/commit/737300348a22c62647cb150308d596f212e6115d))
* **scheduler,maintenance:** error-tolerant ticks + maintenance except-paths ([5af2b5b](https://github.com/mohamed-rekiba/arvel/commit/5af2b5b36f6a7f5d73da1ab36312e3a93e3b61ee))
* **scheduling:** scope onOneServer election lock per minute ([ba1d911](https://github.com/mohamed-rekiba/arvel/commit/ba1d911aa07718a25287d40aba3ea14ab480abd8))
* **search:** render Meilisearch filters by value type ([f377ebc](https://github.com/mohamed-rekiba/arvel/commit/f377ebc8bd62cb77be04fa88a2caf007fb3d613e))
* **security:** stop non-ASCII tokens from crashing constant-time guards into 500 ([af312aa](https://github.com/mohamed-rekiba/arvel/commit/af312aa9dcf7dc05661cf4a86e051d789be82f79))
* **session:** destroy the old store record on regenerate (WI-011) ([6c7233c](https://github.com/mohamed-rekiba/arvel/commit/6c7233c3a772ecda67d54587ffcae38d81492ccb))
* **session:** hash file-session id to block path traversal ([c13f28b](https://github.com/mohamed-rekiba/arvel/commit/c13f28b45653ee8bf0580da4f62a988906840dc5))
* **shell:** boot lazily so the REPL opens when the DB is down ([4538a40](https://github.com/mohamed-rekiba/arvel/commit/4538a4031f2352280803fbcba92f1122431585a5))
* **shell:** scope REPL boot to non-HTTP subsystems ([fe2e429](https://github.com/mohamed-rekiba/arvel/commit/fe2e429cb53311999b07f54dc5f7da60fdfbfa53))
* **skeleton:** map APP_KEY into config app.key ([f2f9603](https://github.com/mohamed-rekiba/arvel/commit/f2f9603ba61f66d75277b913a4bf757cf289d822))
* **skeleton:** move observability config skeleton out of workspace root ([ee1d5d5](https://github.com/mohamed-rekiba/arvel/commit/ee1d5d55a7e67414dc7fbb936310bc1e4e552ffc))
* **storefront:** remove dead "Specials" nav link ([8811f21](https://github.com/mohamed-rekiba/arvel/commit/8811f2108c3a1431a67dc28d991cbf99dcdf3d72))
* streamline code formatting and exception handling ([61d441f](https://github.com/mohamed-rekiba/arvel/commit/61d441f059dd332359505e8995cd6f859b857d0d))
* **support:** compare Collection intersect/diff by value ([eb08db4](https://github.com/mohamed-rekiba/arvel/commit/eb08db43c3102c0a4aa12da13cc527cc9c9eafbf))
* **support:** serialize datetime/Decimal/UUID/bytes in Collection.to_json ([adb72c0](https://github.com/mohamed-rekiba/arvel/commit/adb72c0b7a0116670a122fd4e461e502cba1d9eb))
* **tests:** simplify assertion for category slug in JSONB mapping test ([82ba34e](https://github.com/mohamed-rekiba/arvel/commit/82ba34e2777ae9e912c70660544a5f90927fdb83))
* **types:** annotate _build_served_asgi with concrete Application for serve_lifespan ([9c81d64](https://github.com/mohamed-rekiba/arvel/commit/9c81d64851f48fedead90f56e895b810d600c9f8))
* **types:** explicit re-export of current_user from http.request ([ab6e0cf](https://github.com/mohamed-rekiba/arvel/commit/ab6e0cf431025c5a76eb79aede3e4093cacfe01a))
* update copyright holder in LICENSE file ([088b9d8](https://github.com/mohamed-rekiba/arvel/commit/088b9d825aafe80c74a4cd777ce80c014c4dd628))
* **validation:** actionable error for exists/unique without a DB session ([eeb073d](https://github.com/mohamed-rekiba/arvel/commit/eeb073dce4e415bdbb00978e6caa1f9cc16f05cd))


### Performance

* **ci:** parallelize test suites and unblock ecommerce-kit emulators ([152c2f5](https://github.com/mohamed-rekiba/arvel/commit/152c2f5630b5241b1b17d863c4d05ff6d7afd2bb))
* **ci:** speed up and align the integration test suites ([8766ca1](https://github.com/mohamed-rekiba/arvel/commit/8766ca108a49cdec1bdc946449f6b11afd1f1589))
* **cli:** lazy-load framework imports and add startup banner ([68c2de9](https://github.com/mohamed-rekiba/arvel/commit/68c2de9be1b2a4c3b9676d650e8cd99ea1c4211c))
* **console:** narrow boot for provider-only queue commands ([ae6f743](https://github.com/mohamed-rekiba/arvel/commit/ae6f74397fcefe190141aa23acf6f64614a60169))
* **image:** offload responsive Pillow work to a worker thread ([3530f3d](https://github.com/mohamed-rekiba/arvel/commit/3530f3d925c954cef185793f5da6ee9ab5720358))
* **permission:** batch role permission loading to kill N+1 ([3428f37](https://github.com/mohamed-rekiba/arvel/commit/3428f373c9b3b2ee41f56cb22f935b5ef59f7734))
* **test:** drop RabbitMQ management plugin from framework emulator ([ec5a934](https://github.com/mohamed-rekiba/arvel/commit/ec5a9342f62aec80d76b1f6a81004e1ed079f835))
* **test:** restore loadfile for kit emulator suite ([e98979b](https://github.com/mohamed-rekiba/arvel/commit/e98979be828456c6503542c48cd1bc3c2374c9fd))
* **test:** revert kit to per-worker emulator stacks ([eb8a460](https://github.com/mohamed-rekiba/arvel/commit/eb8a460c8268766abc50b766ebbaa46c5c82bfaa))
* **test:** seed ecommerce-kit catalog once via template DB ([69b2399](https://github.com/mohamed-rekiba/arvel/commit/69b239960ed5c394069c343c4dc2df35560aef2b))
* **test:** share one emulator stack across kit xdist workers ([78eb4c8](https://github.com/mohamed-rekiba/arvel/commit/78eb4c80e778fe69030430155302dbd41ab7d139))


### Refactors

* **arvel-image:** promote private methods to public API ([badbf33](https://github.com/mohamed-rekiba/arvel/commit/badbf33452ba23fe2e48f8d011a6c3ae7163f8fa))
* **arvent:** rename Eloquent → Arvent ([a84f9dc](https://github.com/mohamed-rekiba/arvel/commit/a84f9dc551617cd6f4f076baa03b4a8c8a31ef86))
* **auth:** read is_verified/is_suspended off Authenticatable ([4bbad8c](https://github.com/mohamed-rekiba/arvel/commit/4bbad8c77e394ad50c5cc7dc33373138e6bb89b8))
* **auth:** return Authenticatable from require_auth and Auth.user ([ed49b16](https://github.com/mohamed-rekiba/arvel/commit/ed49b1632294334eaf5face0b15a837927e1662d))
* **boundaries:** break auth&lt;-&gt;http cycle (unify current_user in support) ([77ab091](https://github.com/mohamed-rekiba/arvel/commit/77ab0914f369bf3fc4d7a6a6dc6f439479c8bd9a))
* **boundaries:** break cache&lt;-&gt;support cycle ([f4ea395](https://github.com/mohamed-rekiba/arvel/commit/f4ea395113e14dbbb04d4e20c89c7f4c26606349))
* **boundaries:** break http&lt;-&gt;pagination and pagination&lt;-&gt;views cycles ([e866405](https://github.com/mohamed-rekiba/arvel/commit/e8664051a41ee021f65dec438f8be649e22ee93f))
* **boundaries:** break http&lt;-&gt;telemetry cycle (prometheus split) ([eb43aa1](https://github.com/mohamed-rekiba/arvel/commit/eb43aa174a3b7dd94ce032ce61b0eda02b0a470e))
* **boundaries:** break kernel-&gt;telemetry and kernel-&gt;http cycles ([d1a2a9b](https://github.com/mohamed-rekiba/arvel/commit/d1a2a9b99998a7ab6f46b0b4f4fd9a60a3fa53ff))
* **boundaries:** drop eager telemetry-&gt;http middleware base ([bfecbc8](https://github.com/mohamed-rekiba/arvel/commit/bfecbc88f48adddd01b6f6b9d3aeddb80e5f337e))
* **config:** drop dead NoPrefix clause; document call() resolution limits ([206c810](https://github.com/mohamed-rekiba/arvel/commit/206c8102499a55ae5d31852c530ec956294598d4))
* **console:** drop unused args param from in-process command dispatch ([77a6342](https://github.com/mohamed-rekiba/arvel/commit/77a6342a51e89f2d8aeca0121f245d37786f3038))
* **console:** make arvel new kit-agnostic with per-kit finalize hook ([e27a522](https://github.com/mohamed-rekiba/arvel/commit/e27a522d52717b562605f0d58be189b78b99f989))
* **console:** promote exec_into and type test fakes for pyright ([a444640](https://github.com/mohamed-rekiba/arvel/commit/a444640e20051a3ade5e97d0d6a88c0a46b472cc))
* **deps:** replace httpx with httpx2 across all packages ([d462305](https://github.com/mohamed-rekiba/arvel/commit/d4623059f05f2bd750183844957426fdabc0b9a4))
* **ecommerce-kit:** adopt JsonResource for product/category responses ([173aed7](https://github.com/mohamed-rekiba/arvel/commit/173aed74841aff35bf423b16d8b309d8fcc4881d))
* **ecommerce-kit:** delete unused admin CRUD lib helpers ([d9dc800](https://github.com/mohamed-rekiba/arvel/commit/d9dc800df3a3550dd6314800455fcb8f508b3019))
* **ecommerce-kit:** delete unused cart/checkout lib helpers ([4810690](https://github.com/mohamed-rekiba/arvel/commit/48106904cad906eec45ec5979050096f301e8938))
* **ecommerce-kit:** drop dead admin list-fetch helpers ([dd1e196](https://github.com/mohamed-rekiba/arvel/commit/dd1e196401d2f8214f162c29d392a6ad5295d8ae))
* **ecommerce-kit:** drop test-driven storefront prefetch calls ([49a1d88](https://github.com/mohamed-rekiba/arvel/commit/49a1d88e49f035c53f38a24aafebd890eec6b96b))
* **ecommerce-kit:** move .env.example and pyproject into backend ([fbda8d0](https://github.com/mohamed-rekiba/arvel/commit/fbda8d0a1aa881daaef7e43922e6bf2e7f4c778c))
* **ecommerce:** centralize catalog visibility in a model scope ([906c8f7](https://github.com/mohamed-rekiba/arvel/commit/906c8f73d7ac0c58d523f4d10a503279d890fe02))
* **ecommerce:** delegate image-upload validation to arvel-image ([51a4581](https://github.com/mohamed-rekiba/arvel/commit/51a45813f520b74c2131a3934e95cea0dde8fb01))
* **ecommerce:** derive is_new and subtotal via model accessors ([6ae9b98](https://github.com/mohamed-rekiba/arvel/commit/6ae9b983f674ad0c711387e0f9125264f49fd3d3))
* **ecommerce:** make admin user detail fully Orval-driven ([48cc1fe](https://github.com/mohamed-rekiba/arvel/commit/48cc1fea599af59b212b058eac5d22d95bd39910))
* **ecommerce:** move tunables into the config layer ([716e47a](https://github.com/mohamed-rekiba/arvel/commit/716e47aff849226487005b348df837cdefdb7475))
* **ecommerce:** validate product FKs with framework Rule.exists ([cff2e84](https://github.com/mohamed-rekiba/arvel/commit/cff2e84de920855c88fbed7dc7472db5773f0552))
* **http:** declare global ASGI middleware like service providers ([a2df6b4](https://github.com/mohamed-rekiba/arvel/commit/a2df6b4b0becea9da6962312c08f824da1b4008f))
* improve code structure and performance across multiple modules ([12442c2](https://github.com/mohamed-rekiba/arvel/commit/12442c215c2f1df494c0d13c64cf7df1f29963bf))
* **kits:** relocate e-commerce demo to kits/arvel-ecommerce-kit ([47598ff](https://github.com/mohamed-rekiba/arvel/commit/47598ffee6d52f206ca09eed71ed8d4963b4b0cb))
* **ProductCard:** improve template structure and readability ([72e5db5](https://github.com/mohamed-rekiba/arvel/commit/72e5db505f7dfc23ee3bed3d94bba29f7dbc58ca))
* **queue,console:** failed-jobs ops live on QueueManager (G2 import boundary) ([b108c65](https://github.com/mohamed-rekiba/arvel/commit/b108c6542aa59be30d8daa7959df0d21209d5795))
* **queue:** QueueManager is now a Manager subclass ([3a9bb14](https://github.com/mohamed-rekiba/arvel/commit/3a9bb142309447f2c7557092d85cb28722ca3a25))


### Documentation

* add API reference, changelog, and contributor-docs link checker ([5a8506a](https://github.com/mohamed-rekiba/arvel/commit/5a8506aae1df1e15f7f8979da56a81f0cc5de696))
* **application:** document best-effort provider shutdown ([fd91687](https://github.com/mohamed-rekiba/arvel/commit/fd9168756a6fdef18e23af6af34457aa0593cffb))
* **cache:** correct database store description to app DB connection ([40c21ab](https://github.com/mohamed-rekiba/arvel/commit/40c21abb5bbda681fb13eb0fbed892f479986068))
* **changelog:** mark local file serving (STORAGE_LOCAL_SERVE) as landed ([0a15f22](https://github.com/mohamed-rekiba/arvel/commit/0a15f2207e132a4bb259fc1a15bf0cd5d1a701b6))
* **changelog:** triage bucket-3 feature gaps against the codebase ([ab36157](https://github.com/mohamed-rekiba/arvel/commit/ab36157d084ca6daeae6703a230e83ad18b87174))
* **cli:** enrich CLI reference with workflows and custom commands ([17dd9fc](https://github.com/mohamed-rekiba/arvel/commit/17dd9fc2cecdf1461f05e6df8bb68307f6789bad))
* **console:** list the new commands (migrate:fresh/refresh, db:wipe, cache:clear, key:generate, storage:link, make:enum/exception/test) ([6da52b1](https://github.com/mohamed-rekiba/arvel/commit/6da52b1d74fc25531f9cb52a1e0642d20a5d7f54))
* **core-concepts:** add quick-start sections across lifecycle docs ([5bcd8e0](https://github.com/mohamed-rekiba/arvel/commit/5bcd8e059e34c09f8b94afea4fcb8574d14ce15f))
* **ecommerce-kit:** remove redundant instructions for running the bundled app ([2fdeb69](https://github.com/mohamed-rekiba/arvel/commit/2fdeb694f04e099396e2c2fb20c3fbb03657ec80))
* **error-handling:** correct ProblemDetailsHandler catch-all note ([4462c76](https://github.com/mohamed-rekiba/arvel/commit/4462c7680d20dcdd5be328f854087dc49ecaff05))
* **features:** enrich feature docs with quick-start workflows ([84cde6b](https://github.com/mohamed-rekiba/arvel/commit/84cde6bd62839a91e488328c55978cec81cc567b))
* fix accuracy drift across guides, features, and packages ([85608bc](https://github.com/mohamed-rekiba/arvel/commit/85608bc89741dfaa88800943bf9cf391a64ed7f7))
* **frontend:** add SPA integration quick-start workflow ([9ce56ef](https://github.com/mohamed-rekiba/arvel/commit/9ce56ef0e46c846672b4f41ab0e8467e5b9886ba))
* **getting-started:** add quick-start paths for install and structure ([e833903](https://github.com/mohamed-rekiba/arvel/commit/e83390368d20f25d522585e9504a30f2276c1eed))
* **kits:** add ecommerce kit quick-start commands ([37c78a8](https://github.com/mohamed-rekiba/arvel/commit/37c78a87e72a166dde539a6532acd38737e7066d))
* **kits:** move e-commerce kit page from Packages to Kits ([e51aaf0](https://github.com/mohamed-rekiba/arvel/commit/e51aaf0b30878f4f827553eebfbdc71387b24eff))
* make the docs consistent with the merged observability features ([a20bdcc](https://github.com/mohamed-rekiba/arvel/commit/a20bdcc1f19543d7fc921b1e24895521af8ec6ba))
* **middleware:** document the declarative global middleware stack ([4f13f76](https://github.com/mohamed-rekiba/arvel/commit/4f13f7610025f700d78ee831ccaf212c7e3133fb))
* **orm:** enhance query builder documentation with local and global scopes examples ([da39175](https://github.com/mohamed-rekiba/arvel/commit/da3917555478556e819b95d1615713ba3e7f773b))
* **orm:** rewrite ORM site docs with richer examples ([24dc043](https://github.com/mohamed-rekiba/arvel/commit/24dc043471d11d2ee2369847d7136459c33228e2))
* **packages:** rewrite companion package docs with richer examples ([955390e](https://github.com/mohamed-rekiba/arvel/commit/955390e9bdf1177f8c51d255f978018d85159361))
* **reference:** add API reference navigation quick-start ([8ce959a](https://github.com/mohamed-rekiba/arvel/commit/8ce959adf9ce5e0c14558b962570ae2a5a02eb32))
* **scheduling:** correct stale note — kernel honors maintenance/outputTo ([01eecec](https://github.com/mohamed-rekiba/arvel/commit/01eececcabb3e6ee8075664ecf487d834fdd8bef))
* **session:** fix stale StartSession example to use SessionCookie/SameSite ([7bcb9a2](https://github.com/mohamed-rekiba/arvel/commit/7bcb9a2665943ec77d79adbf5e86b01039558546))
* **site:** add section hubs, doc map, and cross-links ([97055a1](https://github.com/mohamed-rekiba/arvel/commit/97055a1f1b414d207aca0de67e1654fc463f6d26))
* **spatie:** remove third-party Spatie references ([bf2d682](https://github.com/mohamed-rekiba/arvel/commit/bf2d6824bd23d3c4d6e33dbf08e398ee90795f14))
* sync docs with the features added this round ([c4e29da](https://github.com/mohamed-rekiba/arvel/commit/c4e29dae014e452f39bba73928afa3d916c37e63))
* sync lifecycle, session, and container docs with hardening ([0f2d3b8](https://github.com/mohamed-rekiba/arvel/commit/0f2d3b802a0bd3b27879638975b2a0c1585c0e4c))
* **telemetry:** add a hands-on "new to observability" tour with real output ([09c9ad7](https://github.com/mohamed-rekiba/arvel/commit/09c9ad7c97d54672f6315867f886fb3a67dd5861))
* testing.md integration tier, migrations.md default string length. ([f898c42](https://github.com/mohamed-rekiba/arvel/commit/f898c42340e6601c0d19c58e4559f11d4189075f))
* **the-basics:** add quick-start sections across HTTP fundamentals ([0925510](https://github.com/mohamed-rekiba/arvel/commit/0925510bd8284346b84d752a932d4b66a7eac348))
* **type-safety:** clarify usage of Literal, Enum, and str for closed value sets ([326dd7d](https://github.com/mohamed-rekiba/arvel/commit/326dd7df27a395c4277998f2658ec58bd8a95bb7))

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

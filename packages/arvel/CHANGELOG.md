# Changelog

## [0.27.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.27.0...arvel-v0.27.1) (2026-06-14)


### Bug Fixes

* **arvel:** correct SyslogChannel handler type under mypy platform pruning ([faa6b34](https://github.com/mohamed-rekiba/arvel/commit/faa6b34f95ed1bcbe0058979bc93f5087e1ec742))

## [0.27.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.26.0...arvel-v0.27.0) (2026-06-14)


### Features

* **arvel:** port LogManager + harden Container, Session, and Auth ([072a5e5](https://github.com/mohamed-rekiba/arvel/commit/072a5e5c145e438d2a6d5e00d8fe16363deca486))


### Bug Fixes

* **arvel:** harden container extend, session guard, cookie expiry, and session lifecycle ([bcfe75e](https://github.com/mohamed-rekiba/arvel/commit/bcfe75e811439353e594f8ad5c089e0aa3f63237))
* **arvel:** inject resend rate-limit store into AuthController ([a82565d](https://github.com/mohamed-rekiba/arvel/commit/a82565d958057c2304b59fc92072659ff3865383))

## [0.26.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.25.1...arvel-v0.26.0) (2026-06-11)


### Features

* **session:** honor SESSION_SECURE/SESSION_SAME_SITE and add typed enums ([b92004e](https://github.com/mohamed-rekiba/arvel/commit/b92004ef4df3a25293347a568c6b4ac1231dc193))
* **storage:** implement AzureDriver.temporary_url via SAS token ([fa979c0](https://github.com/mohamed-rekiba/arvel/commit/fa979c087eb98888ff8c2d556c47303c536711df))


### Bug Fixes

* **reverb:** wire the Redis broadcast→Reverb fan-out per ADR-013 §4 ([6bf914f](https://github.com/mohamed-rekiba/arvel/commit/6bf914f9e18518058cdfb661bb0e7521c1d44dbb))


### Refactors

* **console:** drop unused args param from in-process command dispatch ([29d8a8a](https://github.com/mohamed-rekiba/arvel/commit/29d8a8ac30f419015340be54efc4c3acdbfe1303))


### Documentation

* **type-safety:** clarify usage of Literal, Enum, and str for closed value sets ([3b94d42](https://github.com/mohamed-rekiba/arvel/commit/3b94d42beaabbfc0fd46d8219b67598a285f11b6))

## [0.25.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.25.0...arvel-v0.25.1) (2026-06-10)


### Performance

* **ci:** speed up and align the integration test suites ([fde4641](https://github.com/mohamed-rekiba/arvel/commit/fde4641a86fa7fbdfe5cf9779b69a13ebaf20e4c))
* **test:** drop RabbitMQ management plugin from framework emulator ([c64847b](https://github.com/mohamed-rekiba/arvel/commit/c64847ba061c553fc979e12ab623a4bba75f8e41))

## [0.25.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.24.0...arvel-v0.25.0) (2026-06-09)


### Features

* **arvon:** add fluent datetime layer over whenever ([50ea34e](https://github.com/mohamed-rekiba/arvel/commit/50ea34e2ee6ab3510105006f24245ade7a8ed8b8))

## [0.24.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.23.0...arvel-v0.24.0) (2026-06-09)


### Features

* **ecommerce-kit:** customer-role listener, cart stock lock, checkout guard ([0b7bce0](https://github.com/mohamed-rekiba/arvel/commit/0b7bce0c1c96664f4fa45659e66479f8c7f28caf))


### Bug Fixes

* **ecommerce-kit:** harden admin self-delete and category parent_id validation ([511ba5f](https://github.com/mohamed-rekiba/arvel/commit/511ba5f93e55cc928d52631ea56a70fbc0d960ac))

## [0.23.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.22.1...arvel-v0.23.0) (2026-06-09)


### Features

* **auth:** permission guards accept a list with all/any semantics ([b14a303](https://github.com/mohamed-rekiba/arvel/commit/b14a30378debbf62aa052a46f6aafc1ab439644b))

## [0.22.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.22.0...arvel-v0.22.1) (2026-06-09)


### Bug Fixes

* streamline code formatting and exception handling ([4991b3f](https://github.com/mohamed-rekiba/arvel/commit/4991b3f95bc543ff3f94e3b718d02845dda13613))

## [0.22.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.21.0...arvel-v0.22.0) (2026-06-09)


### Features

* **auth:** revoke access tokens and share the login throttle ([1de46d6](https://github.com/mohamed-rekiba/arvel/commit/1de46d68b1dc077f362b2f7d77691caeb86b7f64))
* **http:** add Http facade and Http.fake outbound client ([a458738](https://github.com/mohamed-rekiba/arvel/commit/a4587383b2c2a4675a798e664083115cfd368eeb))
* **http:** add response() and redirect() helpers ([e58cb40](https://github.com/mohamed-rekiba/arvel/commit/e58cb40d8c2a579ee05bda383a9705d2cbb90aeb))
* **http:** consolidate CSRF middlewares and accept more token sources ([da44892](https://github.com/mohamed-rekiba/arvel/commit/da448921fd213ac7c4aac293c2b6c3b4ba6d2a66))
* **http:** trust proxies on the general request path ([446421a](https://github.com/mohamed-rekiba/arvel/commit/446421a2896b97fb1a17da590ac94971ccff25ac))
* **validation:** support nested and wildcard field paths ([817556b](https://github.com/mohamed-rekiba/arvel/commit/817556b02de22877e879df4174ab96a8c82166ea))


### Bug Fixes

* **auth:** resolve AuthController per request, not at boot ([17b41ef](https://github.com/mohamed-rekiba/arvel/commit/17b41ef2ace15fc4583a3ca0e71942d2c1cbc582))
* **skeleton:** move observability config skeleton out of workspace root ([6f16939](https://github.com/mohamed-rekiba/arvel/commit/6f169396b66d798e1fb0d562c871f3b727e6384f))
* **validation:** actionable error for exists/unique without a DB session ([bfdecc9](https://github.com/mohamed-rekiba/arvel/commit/bfdecc9fcecc9cfecb275f9552e94c8e187c0469))

## [0.21.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.20.0...arvel-v0.21.0) (2026-06-08)


### Features

* **orm:** complete QueryMixin parity and use model query shortcuts ([ea77780](https://github.com/mohamed-rekiba/arvel/commit/ea777802adf5fbf46b4b433df4548e2e5ab439fb))
* **validation:** add bail, conditional presence, date rules, custom rules, Rule builders ([faf5391](https://github.com/mohamed-rekiba/arvel/commit/faf53918d3232ea9705215f020880273371b7bf5))


### Bug Fixes

* **auth:** return 403 for an unverified logged-in user, not 401 ([5122890](https://github.com/mohamed-rekiba/arvel/commit/5122890ac7dd224d3e6254e37afc5d41031e7a3b))
* **auth:** run policy before() filters in the Gate ([84d2412](https://github.com/mohamed-rekiba/arvel/commit/84d241243e80064ad1729636a6d7d63456e9b688))
* **cache:** anchor RateLimiter window to the first hit, not the last ([ae1851e](https://github.com/mohamed-rekiba/arvel/commit/ae1851ecd47bf756842def62a5dab6f1e9ebb670))
* **console:** annotate venv re-exec nosec suppressions with rationale ([8b18cef](https://github.com/mohamed-rekiba/arvel/commit/8b18cefe164bbbb303fcfd225fad803eefa120ea))
* **events:** log queued-listener enqueue failures instead of running inline ([10a91e7](https://github.com/mohamed-rekiba/arvel/commit/10a91e79e023c794a01bd113741c2d3888929809))
* **http:** map malformed pagination cursor to 400, not 500 ([88713ac](https://github.com/mohamed-rekiba/arvel/commit/88713ace16e032dbc74625f17ec238795c06ccab))
* **http:** run after-commit callbacks after the session is unbound ([ddea10e](https://github.com/mohamed-rekiba/arvel/commit/ddea10e8eb9e914ba5b5a2f4ff9736ca8b4f2aa2))
* **logging:** redact secrets nested in dicts/lists, not just top-level keys ([e9aaef7](https://github.com/mohamed-rekiba/arvel/commit/e9aaef7dbf38cb86b9ee69d68b5e6056a9990682))
* **migrations:** pre-flight DB check in migrate:fresh/refresh ([b2f142d](https://github.com/mohamed-rekiba/arvel/commit/b2f142d2198ea82d54a095deefb7fde55eccdfee))
* **queue:** reserve-then-ack so a worker crash redelivers the job ([49d2d2b](https://github.com/mohamed-rekiba/arvel/commit/49d2d2ba2d646db141721e3ae5ccffc3f4f0d8d7))
* **routing:** hide __hidden__ on models nested in raw returns ([3362544](https://github.com/mohamed-rekiba/arvel/commit/33625447dcf323c9805ecc8268c4552a82ee0a05))

## [0.20.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.19.6...arvel-v0.20.0) (2026-06-08)


### Features

* **cli:** show boot spinner during framework startup ([522d16a](https://github.com/mohamed-rekiba/arvel/commit/522d16a8ed8ff0bc92c13685ff25054037b3e4ce))


### Bug Fixes

* **routing:** drop redundant list[Any] cast that broke the mypy gate ([6cb078b](https://github.com/mohamed-rekiba/arvel/commit/6cb078b0243d6cb61263b7578bcadcc6268e6247))
* **routing:** honour __hidden__ when a route returns a raw model ([acf2e10](https://github.com/mohamed-rekiba/arvel/commit/acf2e10b33099ff51e33d8c18073b31dbbe7bd5c))
* **security:** stop non-ASCII tokens from crashing constant-time guards into 500 ([3809496](https://github.com/mohamed-rekiba/arvel/commit/380949669caca464acda19749246ba56bf056381))

## [0.19.6](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.19.5...arvel-v0.19.6) (2026-06-08)


### Bug Fixes

* **database:** run seeder after-commit callbacks once rows are committed ([3cf317f](https://github.com/mohamed-rekiba/arvel/commit/3cf317ff189c6fbb48e70f57c726b82e4dec3f67))
* **observability:** stop X-Forwarded-For from bypassing /_health and /_metrics CIDR guards ([86d2609](https://github.com/mohamed-rekiba/arvel/commit/86d2609f1d89356e95fd649a74aa0271419dffe0))

## [0.19.5](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.19.4...arvel-v0.19.5) (2026-06-08)


### Bug Fixes

* **auth:** align password_resets storage name across migration, model, and CLI ([baf613b](https://github.com/mohamed-rekiba/arvel/commit/baf613bf8a0fbe95b1a707f83e0963e556513848))
* **cli:** re-exec into project venv and silence shell route logs ([8c197e6](https://github.com/mohamed-rekiba/arvel/commit/8c197e60f8fefcade493c60779ea5154f418c7a0))
* **permission:** match morph-alias discriminator in role/permission query helpers ([a7f718a](https://github.com/mohamed-rekiba/arvel/commit/a7f718af81bebfc1be23de0bf11b719d7931c739))

## [0.19.4](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.19.3...arvel-v0.19.4) (2026-06-08)


### Bug Fixes

* **shell:** scope REPL boot to non-HTTP subsystems ([a760508](https://github.com/mohamed-rekiba/arvel/commit/a76050826c8f67d99bc5d5c8d95797e1a16b0205))

## [0.19.3](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.19.2...arvel-v0.19.3) (2026-06-08)


### Bug Fixes

* **support:** serialize datetime/Decimal/UUID/bytes in Collection.to_json ([bbb83be](https://github.com/mohamed-rekiba/arvel/commit/bbb83bec50752de676c8049237df733fac98c37f))


### Refactors

* **console:** promote exec_into and type test fakes for pyright ([c5db702](https://github.com/mohamed-rekiba/arvel/commit/c5db702c6c53432df9504423949447d08fc6138e))

## [0.19.2](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.19.1...arvel-v0.19.2) (2026-06-08)


### Bug Fixes

* **orm:** accept Laravel string forms in Model.where/or_where ([571aaa2](https://github.com/mohamed-rekiba/arvel/commit/571aaa284bdc4e1f40ddfa14b6c035ada95f515e))

## [0.19.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.19.0...arvel-v0.19.1) (2026-06-08)


### Bug Fixes

* **shell:** boot lazily so the REPL opens when the DB is down ([494de4c](https://github.com/mohamed-rekiba/arvel/commit/494de4ca39483b9fe51ee14240a5e01e45ed2133))

## [0.19.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.18.1...arvel-v0.19.0) (2026-06-08)


### Features

* **cli:** auto re-exec global arvel into project .venv ([f5ff312](https://github.com/mohamed-rekiba/arvel/commit/f5ff312142dd8e3a19f00873a9352a396bddf4ac))


### Bug Fixes

* **application:** drain every provider on shutdown even when one fails ([4b43806](https://github.com/mohamed-rekiba/arvel/commit/4b438068f450678bca9856b839acccce31f6e8b6))
* **context:** round-trip hidden data through dehydrate/hydrate ([ab7dea1](https://github.com/mohamed-rekiba/arvel/commit/ab7dea17a98a307fd50115469f3e9395aef48784))
* **i18n:** select plural form by locale rule, not raw count ([f61a4a0](https://github.com/mohamed-rekiba/arvel/commit/f61a4a05d5363c9df04718613b2449f254a921ce))

## [0.18.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.18.0...arvel-v0.18.1) (2026-06-08)


### Bug Fixes

* **config:** make dotted dict lookups key-only ([ce1345b](https://github.com/mohamed-rekiba/arvel/commit/ce1345b1d54e76fce9aa4bedbef215747542854e))
* **console:** run async CLI commands on the single event loop ([3474f22](https://github.com/mohamed-rekiba/arvel/commit/3474f222a9c0f6fefb4e05ea0242d176f6c3bdba))
* **container:** resolve async bindings at any depth in amake ([1f812c7](https://github.com/mohamed-rekiba/arvel/commit/1f812c753859b73f304a5e6bea746e99d1b7faaf))
* **encryption:** raise DecryptionError on malformed base64 payloads ([70b5d91](https://github.com/mohamed-rekiba/arvel/commit/70b5d91b768046338a30cb33d9c327cb71e6d2fc))
* **hashing:** make Hash.check and needs_rehash algorithm-aware ([75ebb17](https://github.com/mohamed-rekiba/arvel/commit/75ebb174b8c0cac2aea023da17f133a8a6cba9e1))
* **logging:** redact secret log fields by substring ([daf6aca](https://github.com/mohamed-rekiba/arvel/commit/daf6aca61e02e750cf2270b890ec9391baf15dfd))
* **support:** compare Collection intersect/diff by value ([7c51361](https://github.com/mohamed-rekiba/arvel/commit/7c51361ffcbeae9123f844f65512ae6a1ab08f15))

## [0.18.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.17.3...arvel-v0.18.0) (2026-06-08)


### Features

* **orm:** enhance eager loading to respect soft delete scopes ([dc8e8d3](https://github.com/mohamed-rekiba/arvel/commit/dc8e8d3592bc42b78ba0a2009430c5fc596f7777))


### Bug Fixes

* **broadcasting:** make the default broadcast payload JSON-safe (WI-012) ([f3fb893](https://github.com/mohamed-rekiba/arvel/commit/f3fb893455dc8489d7726d3e58ba508496740cd8))
* **framework:** module-by-module audit hardening (WI-001..010) ([53aa027](https://github.com/mohamed-rekiba/arvel/commit/53aa027ef856b400d0b5bc367acb0e04e66090c7))
* **scheduling:** scope onOneServer election lock per minute ([015a3dc](https://github.com/mohamed-rekiba/arvel/commit/015a3dc2d2fa24ae3417a6aa456cd9d1bc34c18b))
* **session:** destroy the old store record on regenerate (WI-011) ([8565bc5](https://github.com/mohamed-rekiba/arvel/commit/8565bc587cb474e1b2fe7e3fa11062fdce96af9b))


### Refactors

* **deps:** replace httpx with httpx2 across all packages ([0c2f530](https://github.com/mohamed-rekiba/arvel/commit/0c2f5301532487be2aa0d7da37583866d999dab4))

## [0.17.3](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.17.2...arvel-v0.17.3) (2026-06-08)


### Bug Fixes

* **console:** run scaffolded compose uv sync from backend/ ([1ae311a](https://github.com/mohamed-rekiba/arvel/commit/1ae311a285373c09b8b3c341239583735d2e1ee2))
* **mail:** apply global mail.from and render from_name ([f158fb0](https://github.com/mohamed-rekiba/arvel/commit/f158fb08b182d0c9f241ad509b6c832c572da67f))
* **reverb:** correct presence channel protocol semantics ([865f2d6](https://github.com/mohamed-rekiba/arvel/commit/865f2d684254350e8966e1c0dd4002ed0cae84dd))


### Refactors

* **console:** make arvel new kit-agnostic with per-kit finalize hook ([bc8e3a6](https://github.com/mohamed-rekiba/arvel/commit/bc8e3a62375da4752b94b95c5934097d864dfd15))

## [0.17.2](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.17.1...arvel-v0.17.2) (2026-06-07)


### Bug Fixes

* **cache:** drop stale ttl arg from CacheConfig calls ([56d8b6d](https://github.com/mohamed-rekiba/arvel/commit/56d8b6db2d2d202b73c62fb81bc8da82abfde2e1))
* **database:** use dialect-aware JsonB/TsVector in column helpers ([12f4cc3](https://github.com/mohamed-rekiba/arvel/commit/12f4cc3fbae8e61f088f26a0232f039a29fc93bf))
* **queue:** give each job envelope a unique id ([c68d8c7](https://github.com/mohamed-rekiba/arvel/commit/c68d8c7bb098b373f2cc2c3062820a403a5dbcf7))
* **queue:** preserve FIFO within priority in redis driver ([971d539](https://github.com/mohamed-rekiba/arvel/commit/971d53919edd4837d09bf2bca9c192834f358ebd))
* **queue:** store jobs epochs as BIGINT and index pop by priority ([d93c26b](https://github.com/mohamed-rekiba/arvel/commit/d93c26bfc44b64c67103642958a652323eb532f6))

## [0.17.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.17.0...arvel-v0.17.1) (2026-06-07)


### Bug Fixes

* **cache:** redis put(ttl=None) stores forever, drop CACHE_TTL default ([3edcca7](https://github.com/mohamed-rekiba/arvel/commit/3edcca77eb0a14425052ef0f7c2183c240c2a738))
* **console:** run uv sync in the kit's python project dir ([1aea97a](https://github.com/mohamed-rekiba/arvel/commit/1aea97a3aad327612129d7a6d0dcc4f8e74b5ba3))
* **database:** bind json key in where_json_path to prevent SQL injection ([1137b21](https://github.com/mohamed-rekiba/arvel/commit/1137b21e8ce43ba5361f266abeff5bf25c75481a))
* **i18n:** block path traversal in translation loaders ([ae74bb4](https://github.com/mohamed-rekiba/arvel/commit/ae74bb411f139f2e4e38414ec832683e6e1daaae))
* **session:** hash file-session id to block path traversal ([8c79e82](https://github.com/mohamed-rekiba/arvel/commit/8c79e82d2932c1769e9f687abd41e05abf1f616a))

## [0.17.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.16.1...arvel-v0.17.0) (2026-06-07)


### Features

* **application:** add support for custom .env file path and enhance JWT secret validation ([7e023f5](https://github.com/mohamed-rekiba/arvel/commit/7e023f5d153067cb18c26cdaceffbad59d5c0c65))


### Bug Fixes

* **auth:** detect refresh-token reuse and revoke the family ([e76eedd](https://github.com/mohamed-rekiba/arvel/commit/e76eedd897a0e5b464bdd0a01eef1f981718835b))
* **database:** fire retrieved on all read paths; load_missing detects async relations ([d5cfccd](https://github.com/mohamed-rekiba/arvel/commit/d5cfccdf38c3adb0c45ae9ed0710344ecd59f14d))
* **http:** render RFC 7807 problem+json for unhandled errors ([7aba9b7](https://github.com/mohamed-rekiba/arvel/commit/7aba9b79a2d591c85fcb405fec8775ff3af7bf5e))


### Refactors

* **ecommerce-kit:** move .env.example and pyproject into backend ([0e8c137](https://github.com/mohamed-rekiba/arvel/commit/0e8c1375b8fd7dd96cdf9fab7613a117366de843))

## [0.16.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.16.0...arvel-v0.16.1) (2026-06-07)


### Bug Fixes

* **auth:** keep "database" as the canonical provider driver string ([9fd03f6](https://github.com/mohamed-rekiba/arvel/commit/9fd03f681a3ffb8cff04da88be84e90cc4a674e4))

## [0.16.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.15.0...arvel-v0.16.0) (2026-06-07)


### Features

* **cli:** needs-based subsystem bootstrap ([4e5b866](https://github.com/mohamed-rekiba/arvel/commit/4e5b866061423dd2cce99cfb7554ed50e2f1f7ff))
* **testing:** bus/notification fakes + refresh_database + json helpers ([1f2e6ec](https://github.com/mohamed-rekiba/arvel/commit/1f2e6ec4ce44158d2fca2c869b4cec0d0c6090fa))


### Bug Fixes

* **quality:** mypy/pyright cleanup in maintenance + scheduling ([b0bb333](https://github.com/mohamed-rekiba/arvel/commit/b0bb3332944bd096617e769628bf5c56abde3b24))


### Refactors

* **arvent:** rename Eloquent → Arvent ([6d8ca4a](https://github.com/mohamed-rekiba/arvel/commit/6d8ca4a01edf359dfd3106cc4c6167b40be559b7))

## [0.15.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.14.0...arvel-v0.15.0) (2026-06-05)


### Features

* **image,orm:** DX-first media API with strict eager-load morph descriptors ([0f922e9](https://github.com/mohamed-rekiba/arvel/commit/0f922e912f81c1869ac851337f328d0ca8ec3ac8))
* **orm,image:** model-level morph class override; media via framework eager loading ([3c3d600](https://github.com/mohamed-rekiba/arvel/commit/3c3d600fa5d3f95d702cb8e69582d4893cd6591b))

## [0.14.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.13.0...arvel-v0.14.0) (2026-06-03)


### Features

* **config,storage:** config-file cascade and storage:link static serving ([c4b6773](https://github.com/mohamed-rekiba/arvel/commit/c4b67730a0c4c6a4e73720f0f609fd9b4372d6fa))

## [0.13.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.12.0...arvel-v0.13.0) (2026-06-03)


### Features

* **storage:** serve local-disk files at the framework ([653b7c5](https://github.com/mohamed-rekiba/arvel/commit/653b7c59dab6142539fe0bada30d0633eeb4a2f4))

## [0.12.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.11.0...arvel-v0.12.0) (2026-06-02)


### Features

* **cli:** print kit-specific next steps after arvel new ([4311924](https://github.com/mohamed-rekiba/arvel/commit/43119242dc52dba67810f48f927e3a8230d736c4))

## [0.11.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.10.0...arvel-v0.11.0) (2026-06-02)


### Features

* **cli:** add db pre-flight checks and ecommerce-kit healthcheck ([f76de0e](https://github.com/mohamed-rekiba/arvel/commit/f76de0e9e23a940233b5ddd9481d05ae3efc94af))

## [0.10.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.9.4...arvel-v0.10.0) (2026-06-02)


### Features

* **cli:** lazy --help listing and in-project command dispatch ([367ea70](https://github.com/mohamed-rekiba/arvel/commit/367ea7047d7d0f163bb5fa849e82518e7a2d59e1))

## [0.9.4](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.9.3...arvel-v0.9.4) (2026-06-02)


### Performance

* **cli:** lazy-load framework imports and add startup banner ([309bcbf](https://github.com/mohamed-rekiba/arvel/commit/309bcbfecb98041a9866f323335e6edecdf6b6e2))

## [0.9.3](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.9.2...arvel-v0.9.3) (2026-06-02)


### Bug Fixes

* **kits:** localize ecommerce docker-compose for scaffolded projects ([27da3f6](https://github.com/mohamed-rekiba/arvel/commit/27da3f6705f4f2646ec4833d25b709c5311e636b))

## [0.9.2](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.9.1...arvel-v0.9.2) (2026-06-02)


### Bug Fixes

* disable testcontainers ryuk reaper and document CLI scaffold ([ab12be9](https://github.com/mohamed-rekiba/arvel/commit/ab12be9341a2a498f535f1dcae523d0776ab48a4))

## [0.9.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.9.0...arvel-v0.9.1) (2026-06-02)


### Bug Fixes

* bind loopback in serve importability test ([5dc895c](https://github.com/mohamed-rekiba/arvel/commit/5dc895c45d0dc6f4c3bfba0c53eb98e1271620f5))

## [0.9.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.8.0...arvel-v0.9.0) (2026-06-02)


### Features

* **kits:** ship ecommerce kit as a github release download ([4995420](https://github.com/mohamed-rekiba/arvel/commit/499542031dac4694b6cadff9bd3a5ac0d9aee218))

## [0.8.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.7.3...arvel-v0.8.0) (2026-06-02)


### Features

* **cli:** fetch ecommerce kit from github release ([5ece23f](https://github.com/mohamed-rekiba/arvel/commit/5ece23f902f78712f3ba748cd5ed9e4db2ee16ac))

## [0.7.3](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.7.2...arvel-v0.7.3) (2026-06-02)


### Documentation

* add API reference, changelog, and contributor-docs link checker ([d8247e8](https://github.com/mohamed-rekiba/arvel/commit/d8247e8d314c5e9303ae136b812e1dc849ff87d1))

## [0.7.2](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.7.1...arvel-v0.7.2) (2026-06-02)


### Refactors

* **kits:** relocate e-commerce demo to kits/arvel-ecommerce-kit ([6976002](https://github.com/mohamed-rekiba/arvel/commit/6976002ba05edd500e433fa4c3fbc2b08e3d23ea))

## [0.7.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.7.0...arvel-v0.7.1) (2026-06-02)


### Bug Fixes

* resolve test issues and remove outdated RTMs ([31a6a69](https://github.com/mohamed-rekiba/arvel/commit/31a6a69b260f8011d558063839765822cee01047))

## [0.7.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.6.1...arvel-v0.7.0) (2026-06-01)


### Features

* **console:** make:* companion generation + REPL/CLI loop fixes ([9f5571d](https://github.com/mohamed-rekiba/arvel/commit/9f5571d18943c5e909d44ef3955acd202b4c64b4))


### Bug Fixes

* **console:** expose public generate() for make companions ([ca1e204](https://github.com/mohamed-rekiba/arvel/commit/ca1e204ed86c96413ecd42956a3ba7d95960bb4b))
* **console:** reuse boot-imported model modules in shell ([edbf2f8](https://github.com/mohamed-rekiba/arvel/commit/edbf2f8c0c8392f4a8212504a5bacdf3021eeae3))
* resolve skeleton missing dev packages nad database seeder ([80ac1dd](https://github.com/mohamed-rekiba/arvel/commit/80ac1ddff4e727379029fffc26973655882e8e16))

## [0.6.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.6.0...arvel-v0.6.1) (2026-06-01)


### Bug Fixes

* **console:** run serve outside the CLI event loop ([03bc57c](https://github.com/mohamed-rekiba/arvel/commit/03bc57ca713de690249d4e5687d32154e5436d78))

## [0.6.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.5.1...arvel-v0.6.0) (2026-06-01)


### Features

* update package URLs and badge formatting across multiple packages ([f5794fd](https://github.com/mohamed-rekiba/arvel/commit/f5794fd0d2d21f46a93d84b4db1d1ea483fb4b83))

## [0.5.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.5.0...arvel-v0.5.1) (2026-06-01)


### Bug Fixes

* **tests:** resolve pyright strict errors in TestClient/CliRunner usage ([f772a6c](https://github.com/mohamed-rekiba/arvel/commit/f772a6c1d5dfc889d12c93b8c4f4b6c2fbef208e))


### Documentation

* **packages:** point package URLs to arvel.dev docs ([4f8d5bd](https://github.com/mohamed-rekiba/arvel/commit/4f8d5bd0d32c443601cb3f4ced566aa493f6c289))

## [0.5.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-v0.4.0...arvel-v0.5.0) (2026-06-01)


### ⚠ BREAKING CHANGES

* **orm:** has_many_attr removed; FK relations are method-style. QueryMixin.all()/get() now return Sequence[Self] (Model returns ModelCollection[Self]).
* **oauth:** rename arvel-auth-social to arvel-oauth

### Features

* **audit:** audit trail + activity log package (epic 004) ([65639f2](https://github.com/mohamed-rekiba/arvel/commit/65639f2d7f1203ce33bbcf6922bafaae954228f4))
* **auth-social:** OAuth2/OIDC social login package (epic 002) ([db071aa](https://github.com/mohamed-rekiba/arvel/commit/db071aaab991bfd24d7948ba876659375c2cd48e))
* **collections:** add find/only/except_ to base Collection ([39d8510](https://github.com/mohamed-rekiba/arvel/commit/39d8510ea9fb0ef71dcce3aadda36342c9deb744))
* **core:** harden framework foundation (epic 001) ([508a5cc](https://github.com/mohamed-rekiba/arvel/commit/508a5cce49361c37a35093d4ea585b25688be83c))
* **database:** adopt clean model syntax without Mapped wrapper ([2fbff86](https://github.com/mohamed-rekiba/arvel/commit/2fbff8634483e535eedba515b53ae72c41d8fa28))
* **database:** streaming and chunking completeness (005-S10) ([d1a6ada](https://github.com/mohamed-rekiba/arvel/commit/d1a6ada2db48043c4af66c3dc21ff8942302bb02))
* **db:** debugging + query-log parity (005-S11) ([f67dec8](https://github.com/mohamed-rekiba/arvel/commit/f67dec883154e050ded036be391d59ef01d036a2))
* **db:** imperative begin/commit/rollback with savepoints (005-S12) ([c82c5ab](https://github.com/mohamed-rekiba/arvel/commit/c82c5ab7d7a9687520fa6900de3f3dd37f0a42ee))
* initialize v0.4.0 development ([17a7679](https://github.com/mohamed-rekiba/arvel/commit/17a767952043ac3825fbab6b9bee26acffe0856d))
* **observability:** add request-flow logging and domain breadcrumbs ([b3106e4](https://github.com/mohamed-rekiba/arvel/commit/b3106e433bb4eb9c5cb151e68f7df3092328377e))
* **orm:** attribute-level custom cast protocol ([ffb3fb5](https://github.com/mohamed-rekiba/arvel/commit/ffb3fb54afd4ee2ebcba1fdbd853a779c78eda1a))
* **orm:** cast-aware dirty tracking ([bc2914f](https://github.com/mohamed-rekiba/arvel/commit/bc2914f69f2ee02dd63a303e403eb66931d80e01))
* **orm:** chunk_by_id, lazy/cursor streaming, and relation batch writes ([5eec868](https://github.com/mohamed-rekiba/arvel/commit/5eec8689e8ddda9613ce365c1563e868a2a32488))
* **orm:** dirty tracking, $appends, and safe morphOne ([591ec51](https://github.com/mohamed-rekiba/arvel/commit/591ec512ceec77803ccf8d23f5de288b322ba8bd))
* **orm:** Eloquent model + relationship parity (epics 006, 007) ([a801b7b](https://github.com/mohamed-rekiba/arvel/commit/a801b7b5223a63a9c95f104c5232d7257fbe23d0))
* **orm:** Eloquent parity wave — MorphToMany eager-load, QB conditionals, model lifecycle ([cbffa6e](https://github.com/mohamed-rekiba/arvel/commit/cbffa6e25346ea93e7f6c1ef0c6c904ac41be082))
* **orm:** fire events on force_delete/restore, clean replicate defaults ([8ac1f97](https://github.com/mohamed-rekiba/arvel/commit/8ac1f975082e859b00387cf9aa8742eb2ba09c4c))
* **orm:** first_where, where_relation, and Eloquent-faithful bulk writes ([c79fdfd](https://github.com/mohamed-rekiba/arvel/commit/c79fdfd170e01c9fb5e5768fb5d44282ebaed189))
* **orm:** recursive tree relations with one-query eager loading ([c4c3d7b](https://github.com/mohamed-rekiba/arvel/commit/c4c3d7bf55a7b7632090794e1e5fac9c64422da2))
* **orm:** relation saves fire model events; structured sync with pivot attrs ([2e04d73](https://github.com/mohamed-rekiba/arvel/commit/2e04d73f04f35ef3dfd90fd97c2b9e14c464f442))
* **orm:** retry transactions on deadlock/serialization failures ([b31c40b](https://github.com/mohamed-rekiba/arvel/commit/b31c40b43b25ac5d5bd529f221e9758fe428ebd4))
* **orm:** track in-place mutation on json/jsonb columns ([a59b0c9](https://github.com/mohamed-rekiba/arvel/commit/a59b0c9c039d8863e026fb0cca7cbbd89cba7d93))
* **orm:** unify method-style FK relations and ergonomic model API ([56f56f9](https://github.com/mohamed-rekiba/arvel/commit/56f56f99ff1d663955474799159c97bf314599fe))
* **pagination:** HTTP + JSON parity, bidirectional cursors (005-S9) ([149dd3c](https://github.com/mohamed-rekiba/arvel/commit/149dd3cc2277d26063ece918a904567a2768a14f))
* **query:** date/time, LIKE, and join helpers (005-S1/S5/S6) ([c7ec8a0](https://github.com/mohamed-rekiba/arvel/commit/c7ec8a033c7991603ddf9f0fcab8368bb59d013b))
* **query:** subquery FROM/JOIN/SELECT (005-S3) ([7f4c3f5](https://github.com/mohamed-rekiba/arvel/commit/7f4c3f507267813c1f51f09ff6ffb186d2296fb2))
* **query:** WHERE predicate engine + clause polish bundle (005-S13) ([1aedaa2](https://github.com/mohamed-rekiba/arvel/commit/1aedaa2569392f9543b0346c01f24c307e5c5a5a))
* **query:** write-path completeness (005-S8) ([94a12fb](https://github.com/mohamed-rekiba/arvel/commit/94a12fb80bf59deeff88cf349dcfe9fc99645194))
* **routing:** support group-level OpenAPI tags ([dbc5da7](https://github.com/mohamed-rekiba/arvel/commit/dbc5da7b7a754c3f3ca4b80bc8174ad264321a80))
* **search:** Scout-style full-text search package (epic 003) ([6d809c4](https://github.com/mohamed-rekiba/arvel/commit/6d809c4c66dfb5aa110c13e25a32cf52c754a00d))


### Bug Fixes

* **ecommerce-demo:** admin CRUD, OpenAPI tags, and real seed images ([7ae1ff4](https://github.com/mohamed-rekiba/arvel/commit/7ae1ff47136941e5fe1a480591ade75cb3f1defd))
* **http:** map auth exceptions to 401/403 instead of 500 ([e624fde](https://github.com/mohamed-rekiba/arvel/commit/e624fde67a2ae3f1cb3186c02ecce494fefd033f))
* **observability:** show logs on stdout when no OTLP collector is set ([1c0c6f4](https://github.com/mohamed-rekiba/arvel/commit/1c0c6f41728f2f861361d80656e91621f5f128a7))
* **orm:** apply [@mutator](https://github.com/mutator) on write and make bulk delete soft-delete aware ([7d33623](https://github.com/mohamed-rekiba/arvel/commit/7d33623ef7fe3ccc3176f7b10ec3312f6dde8ce6))
* **orm:** fire retrieved on every hydration path ([6700f09](https://github.com/mohamed-rekiba/arvel/commit/6700f09d82fb3459c6bc9902e8841425c5e97e28))
* **orm:** Laravel-faithful fill/get-or-create and non-id PK relations ([e5cccbc](https://github.com/mohamed-rekiba/arvel/commit/e5cccbc0a03186c221e37360deeb826062d13c17))
* **orm:** malformed pagination cursor raises InvalidCursorError ([b35cc13](https://github.com/mohamed-rekiba/arvel/commit/b35cc13455291d8d671345480969d1dbfef97149))
* **orm:** PHP-faithful boolean cast and soft-delete-aware relation counts ([4b49ba9](https://github.com/mohamed-rekiba/arvel/commit/4b49ba97d18d9e22767e74895681c57a37486c32))
* resolve linting issues ([6422105](https://github.com/mohamed-rekiba/arvel/commit/64221052bc21c5380b8a070b390776084ab52520))
* **routing:** bind signed-URL signature to scheme + host ([a69e5b4](https://github.com/mohamed-rekiba/arvel/commit/a69e5b429f27e72246985d8db4595ac6dd4b96c4))
* **tests:** resolve testing issues and update the packages ([e9570ee](https://github.com/mohamed-rekiba/arvel/commit/e9570ee11d21c428a0940a5e99a7470e142533da))


### Refactors

* **comments:** humanize comments and drop process-artifact refs ([091f0a0](https://github.com/mohamed-rekiba/arvel/commit/091f0a01d26560cb7e9588a74fab89dfa643c5de))
* **oauth:** rename arvel-auth-social to arvel-oauth ([0aad8a3](https://github.com/mohamed-rekiba/arvel/commit/0aad8a3cbc5156d5712d3aba23a80f831a53bc2f))
* **orm:** replace mapped_column with column vocabulary helpers ([9a932d0](https://github.com/mohamed-rekiba/arvel/commit/9a932d03eb797220e912dd7d907fa1b47189f53d))


### Documentation

* **arvent:** fix clean-model-syntax examples to match the API ([9b26eac](https://github.com/mohamed-rekiba/arvel/commit/9b26eac37f1d2400acbdebfc6d6ba99fd000cca6))
* parity epics 005/006/007, ADR-017 § 2..125, pipeline registry + stage-log. ([cbffa6e](https://github.com/mohamed-rekiba/arvel/commit/cbffa6e25346ea93e7f6c1ef0c6c904ac41be082))
* rewrite documentation site in Laravel style ([4d3b174](https://github.com/mohamed-rekiba/arvel/commit/4d3b174a0ebf3e178f7cf838f7b193a286d40e92))

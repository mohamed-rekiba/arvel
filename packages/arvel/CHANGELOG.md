# Changelog

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

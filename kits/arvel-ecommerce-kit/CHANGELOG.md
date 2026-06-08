# Changelog

## [1.7.4](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.7.3...arvel-ecommerce-kit-v1.7.4) (2026-06-08)


### Bug Fixes

* **database:** wrap seeders in a database transaction for improved consistency ([dafcd60](https://github.com/mohamed-rekiba/arvel/commit/dafcd60ad29e11f7f91e524ff82affa9175a9b04))

## [1.7.3](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.7.2...arvel-ecommerce-kit-v1.7.3) (2026-06-08)


### Bug Fixes

* **ecommerce-kit:** make seed refresh the catalog view unconditionally ([ebe9a97](https://github.com/mohamed-rekiba/arvel/commit/ebe9a97e0543805e6ef3d9454f43fc8450c61427))
* **framework:** module-by-module audit hardening (WI-001..010) ([53aa027](https://github.com/mohamed-rekiba/arvel/commit/53aa027ef856b400d0b5bc367acb0e04e66090c7))


### Refactors

* **deps:** replace httpx with httpx2 across all packages ([0c2f530](https://github.com/mohamed-rekiba/arvel/commit/0c2f5301532487be2aa0d7da37583866d999dab4))

## [1.7.2](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.7.1...arvel-ecommerce-kit-v1.7.2) (2026-06-07)


### Refactors

* **ecommerce-kit:** move .env.example and pyproject into backend ([0e8c137](https://github.com/mohamed-rekiba/arvel/commit/0e8c1375b8fd7dd96cdf9fab7613a117366de843))

## [1.7.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.7.0...arvel-ecommerce-kit-v1.7.1) (2026-06-07)


### Bug Fixes

* **storefront:** remove dead "Specials" nav link ([1d1ecb3](https://github.com/mohamed-rekiba/arvel/commit/1d1ecb3c8365e0dbc40a705cad7b7fd4ffc6a78c))

## [1.7.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.6.0...arvel-ecommerce-kit-v1.7.0) (2026-06-07)


### Features

* **cli:** needs-based subsystem bootstrap ([4e5b866](https://github.com/mohamed-rekiba/arvel/commit/4e5b866061423dd2cce99cfb7554ed50e2f1f7ff))


### Documentation

* **spatie:** remove third-party Spatie references ([8ac870e](https://github.com/mohamed-rekiba/arvel/commit/8ac870ee10dd0cf6d980d3b8d267daa65a5270c4))

## [1.6.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.5.1...arvel-ecommerce-kit-v1.6.0) (2026-06-05)


### Features

* **arvel-image:** responsive images, manipulations, and package audit hardening ([d71a609](https://github.com/mohamed-rekiba/arvel/commit/d71a609443ddb32eeb87643d7842b3a192d398f4))
* **ecommerce-kit:** use full arvel-image feature set E2E ([b4a634f](https://github.com/mohamed-rekiba/arvel/commit/b4a634fa588b5fd28e7adf82a088f0921c7bd919))
* **image,orm:** DX-first media API with strict eager-load morph descriptors ([0f922e9](https://github.com/mohamed-rekiba/arvel/commit/0f922e912f81c1869ac851337f328d0ca8ec3ac8))
* **kit:** multiple product images on detail page ([c6c2bdc](https://github.com/mohamed-rekiba/arvel/commit/c6c2bdceaf91a2057d5c65c4f1b539ed927dbd74))
* **orm,image:** model-level morph class override; media via framework eager loading ([3c3d600](https://github.com/mohamed-rekiba/arvel/commit/3c3d600fa5d3f95d702cb8e69582d4893cd6591b))


### Bug Fixes

* **ci/gitleaks:** allowlist valkey image-tag entropy + repair renamed-test path ([3760d42](https://github.com/mohamed-rekiba/arvel/commit/3760d427fdf1c9dcb1805beaefc6577f7999f01a))
* **ecommerce-kit/frontend:** stop cart re-render, link product, upgrade orval to 8 ([1cd32e4](https://github.com/mohamed-rekiba/arvel/commit/1cd32e4865b545696f45567961bde309d233b518))
* **ecommerce-kit:** use os.urandom noise in _make_jpeg so responsive srcset is non-empty ([dfa13ba](https://github.com/mohamed-rekiba/arvel/commit/dfa13ba93c6f7dd41d4ea8f4a47e7c17164a3823))
* **kit/services:** remove hard-coded conversion lists and dead seeder fallback ([8a9d967](https://github.com/mohamed-rekiba/arvel/commit/8a9d967bdf60a0c88c3187d76290ec7bde31ad31))

## [1.5.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.5.0...arvel-ecommerce-kit-v1.5.1) (2026-06-03)


### Bug Fixes

* **ecommerce-kit:** point feature-test cache at testcontainer Redis ([6d6be41](https://github.com/mohamed-rekiba/arvel/commit/6d6be41b7569459a6d69b501f3dc42b9a9878c22))

## [1.5.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.4.0...arvel-ecommerce-kit-v1.5.0) (2026-06-03)


### Features

* **storage:** serve local-disk files at the framework ([653b7c5](https://github.com/mohamed-rekiba/arvel/commit/653b7c59dab6142539fe0bada30d0633eeb4a2f4))

## [1.4.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.3.0...arvel-ecommerce-kit-v1.4.0) (2026-06-02)


### Features

* **ecommerce-kit:** add Windows healthcheck script and OS-aware make target ([f855d39](https://github.com/mohamed-rekiba/arvel/commit/f855d39698a657937c6d2bb72aff161568d8c443))

## [1.3.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.2.3...arvel-ecommerce-kit-v1.3.0) (2026-06-02)


### Features

* **cli:** add db pre-flight checks and ecommerce-kit healthcheck ([f76de0e](https://github.com/mohamed-rekiba/arvel/commit/f76de0e9e23a940233b5ddd9481d05ae3efc94af))

## [1.2.3](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.2.2...arvel-ecommerce-kit-v1.2.3) (2026-06-02)


### Bug Fixes

* **kits:** localize ecommerce docker-compose for scaffolded projects ([27da3f6](https://github.com/mohamed-rekiba/arvel/commit/27da3f6705f4f2646ec4833d25b709c5311e636b))

## [1.2.2](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.2.1...arvel-ecommerce-kit-v1.2.2) (2026-06-02)


### Bug Fixes

* **kits:** unbreak ecommerce kit dependency resolution ([5dcd557](https://github.com/mohamed-rekiba/arvel/commit/5dcd557d13547c692ac792fd2b3060e9321fff89))

## [1.2.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.2.0...arvel-ecommerce-kit-v1.2.1) (2026-06-02)


### Bug Fixes

* disable testcontainers ryuk reaper and document CLI scaffold ([ab12be9](https://github.com/mohamed-rekiba/arvel/commit/ab12be9341a2a498f535f1dcae523d0776ab48a4))

## [1.2.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.1.0...arvel-ecommerce-kit-v1.2.0) (2026-06-02)


### Features

* **kits:** ship ecommerce kit as a github release download ([4995420](https://github.com/mohamed-rekiba/arvel/commit/499542031dac4694b6cadff9bd3a5ac0d9aee218))


### Bug Fixes

* **kits:** route unauthenticated admin visitors to admin login ([a52eaf4](https://github.com/mohamed-rekiba/arvel/commit/a52eaf4a736718bb77efbaac382d8fbfd12d463b))

## [1.1.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-ecommerce-kit-v1.0.0...arvel-ecommerce-kit-v1.1.0) (2026-06-02)


### Features

* **cli:** fetch ecommerce kit from github release ([5ece23f](https://github.com/mohamed-rekiba/arvel/commit/5ece23f902f78712f3ba748cd5ed9e4db2ee16ac))


### Refactors

* **kits:** relocate e-commerce demo to kits/arvel-ecommerce-kit ([6976002](https://github.com/mohamed-rekiba/arvel/commit/6976002ba05edd500e433fa4c3fbc2b08e3d23ea))

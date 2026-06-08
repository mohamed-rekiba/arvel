# Changelog

## [0.6.3](https://github.com/mohamed-rekiba/arvel/compare/arvel-oauth-v0.6.2...arvel-oauth-v0.6.3) (2026-06-08)


### Bug Fixes

* **oauth:** default Microsoft email_verified to false when claim absent ([2ed3e50](https://github.com/mohamed-rekiba/arvel/commit/2ed3e508513badaf2b0569f29035f4bcac7545d5))

## [0.6.2](https://github.com/mohamed-rekiba/arvel/compare/arvel-oauth-v0.6.1...arvel-oauth-v0.6.2) (2026-06-08)


### Refactors

* **deps:** replace httpx with httpx2 across all packages ([0c2f530](https://github.com/mohamed-rekiba/arvel/commit/0c2f5301532487be2aa0d7da37583866d999dab4))

## [0.6.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-oauth-v0.6.0...arvel-oauth-v0.6.1) (2026-06-07)


### Documentation

* **spatie:** remove third-party Spatie references ([8ac870e](https://github.com/mohamed-rekiba/arvel/commit/8ac870ee10dd0cf6d980d3b8d267daa65a5270c4))

## [0.6.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-oauth-v0.5.1...arvel-oauth-v0.6.0) (2026-06-01)


### Features

* update package URLs and badge formatting across multiple packages ([f5794fd](https://github.com/mohamed-rekiba/arvel/commit/f5794fd0d2d21f46a93d84b4db1d1ea483fb4b83))

## [0.5.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-oauth-v0.5.0...arvel-oauth-v0.5.1) (2026-06-01)


### Bug Fixes

* **tests:** resolve pyright strict errors in TestClient/CliRunner usage ([f772a6c](https://github.com/mohamed-rekiba/arvel/commit/f772a6c1d5dfc889d12c93b8c4f4b6c2fbef208e))


### Documentation

* **packages:** point package URLs to arvel.dev docs ([4f8d5bd](https://github.com/mohamed-rekiba/arvel/commit/4f8d5bd0d32c443601cb3f4ced566aa493f6c289))

## [0.5.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-oauth-v0.4.0...arvel-oauth-v0.5.0) (2026-06-01)


### ⚠ BREAKING CHANGES

* **orm:** has_many_attr removed; FK relations are method-style. QueryMixin.all()/get() now return Sequence[Self] (Model returns ModelCollection[Self]).
* **oauth:** rename arvel-auth-social to arvel-oauth

### Features

* **database:** adopt clean model syntax without Mapped wrapper ([2fbff86](https://github.com/mohamed-rekiba/arvel/commit/2fbff8634483e535eedba515b53ae72c41d8fa28))
* **orm:** unify method-style FK relations and ergonomic model API ([56f56f9](https://github.com/mohamed-rekiba/arvel/commit/56f56f99ff1d663955474799159c97bf314599fe))


### Bug Fixes

* **oauth:** verify Apple id_token signature against JWKS ([3fefec7](https://github.com/mohamed-rekiba/arvel/commit/3fefec79aee2073aceeb49b18b6dfd0ce57e78b4))
* **tests:** resolve testing issues and update the packages ([e9570ee](https://github.com/mohamed-rekiba/arvel/commit/e9570ee11d21c428a0940a5e99a7470e142533da))


### Refactors

* **oauth:** rename arvel-auth-social to arvel-oauth ([0aad8a3](https://github.com/mohamed-rekiba/arvel/commit/0aad8a3cbc5156d5712d3aba23a80f831a53bc2f))
* **orm:** replace mapped_column with column vocabulary helpers ([9a932d0](https://github.com/mohamed-rekiba/arvel/commit/9a932d03eb797220e912dd7d907fa1b47189f53d))


### Documentation

* rewrite documentation site in Laravel style ([4d3b174](https://github.com/mohamed-rekiba/arvel/commit/4d3b174a0ebf3e178f7cf838f7b193a286d40e92))

# Changelog

## [0.6.3](https://github.com/mohamed-rekiba/arvel/compare/arvel-permission-v0.6.2...arvel-permission-v0.6.3) (2026-06-07)


### Bug Fixes

* **permission:** make role/permission middleware work with Arvel pipeline ([a46519a](https://github.com/mohamed-rekiba/arvel/commit/a46519ac6458889e3b27bbe2b82555d92595629b))

## [0.6.2](https://github.com/mohamed-rekiba/arvel/compare/arvel-permission-v0.6.1...arvel-permission-v0.6.2) (2026-06-07)


### Documentation

* **spatie:** remove third-party Spatie references ([8ac870e](https://github.com/mohamed-rekiba/arvel/commit/8ac870ee10dd0cf6d980d3b8d267daa65a5270c4))

## [0.6.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-permission-v0.6.0...arvel-permission-v0.6.1) (2026-06-02)


### Bug Fixes

* **docs:** update module description for clarity and accuracy ([266502a](https://github.com/mohamed-rekiba/arvel/commit/266502a951b545d2ae4c0c1d4d66f5b72c1c18f7))

## [0.6.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-permission-v0.5.1...arvel-permission-v0.6.0) (2026-06-01)


### Features

* update package URLs and badge formatting across multiple packages ([f5794fd](https://github.com/mohamed-rekiba/arvel/commit/f5794fd0d2d21f46a93d84b4db1d1ea483fb4b83))

## [0.5.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-permission-v0.5.0...arvel-permission-v0.5.1) (2026-06-01)


### Documentation

* **packages:** point package URLs to arvel.dev docs ([4f8d5bd](https://github.com/mohamed-rekiba/arvel/commit/4f8d5bd0d32c443601cb3f4ced566aa493f6c289))

## [0.5.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-permission-v0.4.0...arvel-permission-v0.5.0) (2026-06-01)


### ⚠ BREAKING CHANGES

* **orm:** has_many_attr removed; FK relations are method-style. QueryMixin.all()/get() now return Sequence[Self] (Model returns ModelCollection[Self]).

### Features

* **database:** adopt clean model syntax without Mapped wrapper ([2fbff86](https://github.com/mohamed-rekiba/arvel/commit/2fbff8634483e535eedba515b53ae72c41d8fa28))
* initialize v0.4.0 development ([17a7679](https://github.com/mohamed-rekiba/arvel/commit/17a767952043ac3825fbab6b9bee26acffe0856d))
* **orm:** Eloquent parity wave — MorphToMany eager-load, QB conditionals, model lifecycle ([cbffa6e](https://github.com/mohamed-rekiba/arvel/commit/cbffa6e25346ea93e7f6c1ef0c6c904ac41be082))
* **orm:** unify method-style FK relations and ergonomic model API ([56f56f9](https://github.com/mohamed-rekiba/arvel/commit/56f56f99ff1d663955474799159c97bf314599fe))


### Bug Fixes

* **tests:** resolve testing issues and update the packages ([e9570ee](https://github.com/mohamed-rekiba/arvel/commit/e9570ee11d21c428a0940a5e99a7470e142533da))


### Documentation

* parity epics 005/006/007, ADR-017 § 2..125, pipeline registry + stage-log. ([cbffa6e](https://github.com/mohamed-rekiba/arvel/commit/cbffa6e25346ea93e7f6c1ef0c6c904ac41be082))
* rewrite documentation site in Laravel style ([4d3b174](https://github.com/mohamed-rekiba/arvel/commit/4d3b174a0ebf3e178f7cf838f7b193a286d40e92))

# Changelog

## [0.7.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-image-v0.6.1...arvel-image-v0.7.0) (2026-06-02)


### Features

* **cli:** fetch ecommerce kit from github release ([5ece23f](https://github.com/mohamed-rekiba/arvel/commit/5ece23f902f78712f3ba748cd5ed9e4db2ee16ac))

## [0.6.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-image-v0.6.0...arvel-image-v0.6.1) (2026-06-02)


### Bug Fixes

* resolve test issues and remove outdated RTMs ([31a6a69](https://github.com/mohamed-rekiba/arvel/commit/31a6a69b260f8011d558063839765822cee01047))

## [0.6.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-image-v0.5.1...arvel-image-v0.6.0) (2026-06-01)


### Features

* update package URLs and badge formatting across multiple packages ([f5794fd](https://github.com/mohamed-rekiba/arvel/commit/f5794fd0d2d21f46a93d84b4db1d1ea483fb4b83))

## [0.5.1](https://github.com/mohamed-rekiba/arvel/compare/arvel-image-v0.5.0...arvel-image-v0.5.1) (2026-06-01)


### Documentation

* **packages:** point package URLs to arvel.dev docs ([4f8d5bd](https://github.com/mohamed-rekiba/arvel/commit/4f8d5bd0d32c443601cb3f4ced566aa493f6c289))

## [0.5.0](https://github.com/mohamed-rekiba/arvel/compare/arvel-image-v0.4.0...arvel-image-v0.5.0) (2026-06-01)


### ⚠ BREAKING CHANGES

* **orm:** has_many_attr removed; FK relations are method-style. QueryMixin.all()/get() now return Sequence[Self] (Model returns ModelCollection[Self]).

### Features

* **database:** adopt clean model syntax without Mapped wrapper ([2fbff86](https://github.com/mohamed-rekiba/arvel/commit/2fbff8634483e535eedba515b53ae72c41d8fa28))
* **image:** lazy Image chain with async terminals ([c158dc9](https://github.com/mohamed-rekiba/arvel/commit/c158dc9638c10b2f08af630a70a88dc19f2da3a1))
* initialize v0.4.0 development ([17a7679](https://github.com/mohamed-rekiba/arvel/commit/17a767952043ac3825fbab6b9bee26acffe0856d))
* **orm:** Eloquent parity wave — MorphToMany eager-load, QB conditionals, model lifecycle ([cbffa6e](https://github.com/mohamed-rekiba/arvel/commit/cbffa6e25346ea93e7f6c1ef0c6c904ac41be082))
* **orm:** unify method-style FK relations and ergonomic model API ([56f56f9](https://github.com/mohamed-rekiba/arvel/commit/56f56f99ff1d663955474799159c97bf314599fe))


### Documentation

* parity epics 005/006/007, ADR-122..125, pipeline registry + stage-log. ([cbffa6e](https://github.com/mohamed-rekiba/arvel/commit/cbffa6e25346ea93e7f6c1ef0c6c904ac41be082))
* rewrite documentation site in Laravel style ([4d3b174](https://github.com/mohamed-rekiba/arvel/commit/4d3b174a0ebf3e178f7cf838f7b193a286d40e92))

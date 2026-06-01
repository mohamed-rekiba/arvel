# Changelog

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

* parity epics 005/006/007, ADR-122..125, pipeline registry + stage-log. ([cbffa6e](https://github.com/mohamed-rekiba/arvel/commit/cbffa6e25346ea93e7f6c1ef0c6c904ac41be082))
* rewrite documentation site in Laravel style ([4d3b174](https://github.com/mohamed-rekiba/arvel/commit/4d3b174a0ebf3e178f7cf838f7b193a286d40e92))

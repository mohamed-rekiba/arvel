# Changelog

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

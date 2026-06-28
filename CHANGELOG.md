# Changelog

## [0.42.0](https://github.com/mohamed-rekiba/arvel/compare/v0.41.0...v0.42.0) (2026-06-28)


### Features

* **telemetry:** auto-instrument HTTP requests with OpenTelemetry server spans ([28a8a1a](https://github.com/mohamed-rekiba/arvel/commit/28a8a1ae45505176041ff9623990385ffcae94b7))
* **telemetry:** export metrics and logs alongside traces (full OTLP signal set) ([e7adf38](https://github.com/mohamed-rekiba/arvel/commit/e7adf3853e2c34d9dbe34b7e81915c3e23f8d96c))

## [0.41.0](https://github.com/mohamed-rekiba/arvel/compare/v0.40.0...v0.41.0) (2026-06-28)


### Features

* **telemetry:** OpenTelemetry tracing wired from config, backend-agnostic via OTLP ([538efae](https://github.com/mohamed-rekiba/arvel/commit/538efae1d7021dbe9106c1c43f0d47025411d34c))


### Bug Fixes

* **queue:** reserve delayed jobs atomically so concurrent workers never double-release ([a59b6ac](https://github.com/mohamed-rekiba/arvel/commit/a59b6ac3755fcb7b3da4881b487c984a33be14ee))

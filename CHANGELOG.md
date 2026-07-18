# Changelog

## [0.3.0](https://github.com/comfort-hub/delonghi-comfort/compare/v0.2.3...v0.3.0) (2026-07-18)


### ⚠ BREAKING CHANGES

* Command is a generic dataclass not a StrEnum; constants moved to Commands; COMMAND_FIELDS removed.

### Features

* type commands with a generic Command[T] and value encoders ([0b65a4a](https://github.com/comfort-hub/delonghi-comfort/commit/0b65a4ae177a2dfd9baf3e58d2ba5e24c33377be))

## [0.2.3](https://github.com/comfort-hub/delonghi-comfort/compare/v0.2.2...v0.2.3) (2026-07-18)


### Features

* add timezone (TMZone) setter and fill test-coverage gaps ([#11](https://github.com/comfort-hub/delonghi-comfort/issues/11), [#13](https://github.com/comfort-hub/delonghi-comfort/issues/13)) ([e1f149c](https://github.com/comfort-hub/delonghi-comfort/commit/e1f149cbf58f7fbffd88c8d6f8bcc24ea72f25cb))

## [0.2.2](https://github.com/comfort-hub/delonghi-comfort/compare/v0.2.1...v0.2.2) (2026-07-18)


### Features

* add a unit argument to async_set_temperature ([56fe789](https://github.com/comfort-hub/delonghi-comfort/commit/56fe789126b108094d966ab8ca2054d9627e0611))

## [0.2.1](https://github.com/comfort-hub/delonghi-comfort/compare/v0.2.0...v0.2.1) (2026-07-18)


### Features

* add async_discover for cross-region device discovery ([d9e8d4d](https://github.com/comfort-hub/delonghi-comfort/commit/d9e8d4d6ae15c93698b8b562dc65bb14bb6b0401))

## [0.2.0](https://github.com/comfort-hub/delonghi-comfort/compare/v0.1.0...v0.2.0) (2026-07-18)


### ⚠ BREAKING CHANGES

* temperature-setting APIs take a TemperatureUnit enum instead of a `celsius: bool`.

### Features

* add schedule-enable and temp-unit commands + telemetry models ([3dc7ece](https://github.com/comfort-hub/delonghi-comfort/commit/3dc7ece6faa7f84e3715e5c1a595070277c8f3db))


### Bug Fixes

* harden the MQTT transport against listener errors and reconnects ([a765fe9](https://github.com/comfort-hub/delonghi-comfort/commit/a765fe9d8167111e3f91fd72890b2f358e04687e))
* make Gigya auth resilient to gateway errors and rate limits ([d50c186](https://github.com/comfort-hub/delonghi-comfort/commit/d50c1861c71611c1fac0440812a1df459c77859c))

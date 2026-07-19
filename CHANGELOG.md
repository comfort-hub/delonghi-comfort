# Changelog

## [0.3.6](https://github.com/comfort-hub/delonghi-comfort/compare/v0.3.5...v0.3.6) (2026-07-19)


### Features

* retry transient cloud failures and build TLS off the event loop ([#38](https://github.com/comfort-hub/delonghi-comfort/issues/38)) ([be8f61a](https://github.com/comfort-hub/delonghi-comfort/commit/be8f61a360293b56afc6a0416d6eea42546659cc))

## [0.3.5](https://github.com/comfort-hub/delonghi-comfort/compare/v0.3.4...v0.3.5) (2026-07-19)


### Bug Fixes

* reset shadow version on disconnect so reconnects re-baseline ([#36](https://github.com/comfort-hub/delonghi-comfort/issues/36)) ([af77c42](https://github.com/comfort-hub/delonghi-comfort/commit/af77c4252c7da3bd910ad0cb2a16259daddef736))

## [0.3.4](https://github.com/comfort-hub/delonghi-comfort/compare/v0.3.3...v0.3.4) (2026-07-19)


### Features

* version-gate shadow updates to drop stale/duplicate messages ([#34](https://github.com/comfort-hub/delonghi-comfort/issues/34)) ([8fdc33a](https://github.com/comfort-hub/delonghi-comfort/commit/8fdc33a09cc521f4aa23c731229bcc8bb29f992d))

## [0.3.3](https://github.com/comfort-hub/delonghi-comfort/compare/v0.3.2...v0.3.3) (2026-07-19)


### Features

* refresh shadow on reconnect and expose report-time staleness ([#32](https://github.com/comfort-hub/delonghi-comfort/issues/32)) ([03bd352](https://github.com/comfort-hub/delonghi-comfort/commit/03bd352992f790b232a07139bfadc5e22c858778))

## [0.3.2](https://github.com/comfort-hub/delonghi-comfort/compare/v0.3.1...v0.3.2) (2026-07-18)


### Features

* expose typed connection-state events ([a85a0cb](https://github.com/comfort-hub/delonghi-comfort/commit/a85a0cb5500ae7cfeee9df7355102371d5f96735))

## [0.3.1](https://github.com/comfort-hub/delonghi-comfort/compare/v0.3.0...v0.3.1) (2026-07-18)


### Bug Fixes

* expose add_error_listener on the client ([#3](https://github.com/comfort-hub/delonghi-comfort/issues/3)) ([56b595e](https://github.com/comfort-hub/delonghi-comfort/commit/56b595e6120a26e4428b3aa873b31bb87558f6ef))

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

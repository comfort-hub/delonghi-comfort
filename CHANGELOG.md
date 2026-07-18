# Changelog

## [0.2.0](https://github.com/comfort-hub/delonghi-comfort/compare/v0.1.0...v0.2.0) (2026-07-18)


### ⚠ BREAKING CHANGES

* temperature-setting APIs take a TemperatureUnit enum instead of a `celsius: bool`.

### Features

* add schedule-enable and temp-unit commands + telemetry models ([3dc7ece](https://github.com/comfort-hub/delonghi-comfort/commit/3dc7ece6faa7f84e3715e5c1a595070277c8f3db))


### Bug Fixes

* harden the MQTT transport against listener errors and reconnects ([a765fe9](https://github.com/comfort-hub/delonghi-comfort/commit/a765fe9d8167111e3f91fd72890b2f358e04687e))
* make Gigya auth resilient to gateway errors and rate limits ([d50c186](https://github.com/comfort-hub/delonghi-comfort/commit/d50c1861c71611c1fac0440812a1df459c77859c))

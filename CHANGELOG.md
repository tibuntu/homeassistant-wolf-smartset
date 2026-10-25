# Changelog

## [0.2.0](https://github.com/tibuntu/homeassistant-wolf-smartset/compare/v0.1.0...v0.2.0) (2026-10-25)


### Features

* block repeated logins after a failure, typed Maintenance error ([26490e4](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/26490e4e4119134c36b71be62be537ac75328b03))
* brand icons in a light and a dark variant ([bdc9629](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/bdc9629808c0f92ccfec5ae6c855b716d8b43c3b))
* keep the redacted write response in the history record ([04d56c2](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/04d56c2cd8b460df9853e8e4ff71154564a417f9))
* read-only MVP of the wolf_smartset integration ([522ae33](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/522ae336a647f86c3f226aa91bf67e5ffe68bdb3))
* write pipeline with dry run, no-op check, rate limit, lock, history and undo ([b540cee](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/b540cee4c6ac88660b6c35c40a3be9da4df21408))


### Bug Fixes

* blank values of identifying parameters when recording fixtures ([58a23fb](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/58a23fbab1791d82ab9109cf8759cd8fc28af3c8))
* count a rejected fresh token as a failed login ([641b1d5](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/641b1d56dd59ead0972cd9b72c564cfe0711ec04))
* count the hourly write budget from the persisted history ([c1e7c82](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/c1e7c82cc6fc8159908a68fd144a05e4ad9f9bc8))
* failed writes count towards the hourly budget ([962e6e5](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/962e6e5c07c0cc4de4d065263a28a2e708e91ed5))
* keep written values for 30 s and record confirmed/read_back explicitly ([c31b7b0](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/c31b7b093ffbab9d60c705ff5a664c9810aeb52c))
* known switches need write access, otherwise they are enum sensors ([36dd355](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/36dd355977405a54603260e1156032464181fe53))
* no-op check accepts comma decimals like validation does ([32e2853](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/32e2853c9f9312e9a68dd813c1e024a906a043f7))
* numeric inputs without a step width are sensors, no step fallback ([f4fdad8](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/f4fdad80d3362b96136726597510c72a946584cc))
* own HTTP client and via_device_id instead of deprecated APIs ([f9f840f](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/f9f840fa17a89ab58ebd18509603471052227955))
* raise the wolflink issue only for the same account ([a295026](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/a2950267b2db54fc4bdd9dba77a93f9af94e9211))
* read the schema configuration, drop the prefix device rule, version 0.2.0.dev1 ([378b3f7](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/378b3f7c9fd3ad246e76a76ebf162adb7d19f69a))
* redact every identifying key in stored write responses ([1364abd](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/1364abd186ab84b1ff671d2ffff6d271abec188d))
* refuse writes while the access level is unknown ([7ff7ef7](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/7ff7ef723cd020f8471b84ba13574d75a08c4900))
* skip tabs without a BundleId instead of guessing 1000 ([57f2dca](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/57f2dcad6385b86ee7de1cb59dcafe8e0a45d7cd))
* snapshot state class, device by ValueId prefix, Wolf labels, sensible defaults ([ae0cf2a](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/ae0cf2aae3edabf4fd15c2b9867dfc89dd8b9bca))
* the login block survives Home Assistant restarts ([b94c4f3](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/b94c4f379542a1981e735ca64b720b610ad96548))
* translated error for unparsable numbers, no signed zero ([0c915a0](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/0c915a0a9a9a34aeb7e252b5d82101ed81d84c6b))

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
* translated error for unparsable numbers, no signed zero ([0c915a0](https://github.com/tibuntu/homeassistant-wolf-smartset/commit/0c915a0a9a9a34aeb7e252b5d82101ed81d84c6b))

## Changelog

## Unreleased (planned as 0.2.0)

### Added

- **Brand icon** in a light and a dark variant, shown in the integrations list.
- **Writing** for `number`, `select` and the "1x Warmwasser" switch, through one pipeline with dry run (on by default), no-op suppression, validation, access-level check, rate limit (20 per hour, configurable), lock, optimistic state and a persistent history ([ADR-Writes-013](docs/adr/ADR-Writes-013-write-pipeline-with-explicit-confirmation.md)). The written value is kept for 30 s, even if a poll that ran during or right after the write still returns the old value. The first poll after that confirms or corrects it. Every applied write records `confirmed` (`null` while pending, `true` or `false`) and `read_back`.
- **Undo last change** button.
- **Write history in the diagnostics** (last 50 attempts with result).
- Options "Dry run" and "Maximum writes per hour".

### Fixed

- **No more Home Assistant warnings at setup.** The integration uses its own HTTP client and closes only that one. Sub-devices link to the system device through `via_device_id`; `via_device` stops working in Home Assistant 2027.8.
- **State class of closed-period energy values.** Sensors for a closed period no longer use `total_increasing`, because their value can drop. Home Assistant read every drop as a meter reset and added the new value to the long-term sum. Affected: "Verbrauch Vortag", "Erzeugte Wärmemenge Vortag", "Verbrauch Vorjahr", "Erzeugte Wärmemenge Vorjahr", "Verbrauch Vorvorjahr", "Erzeugte Wärmemenge Vorvorjahr". They keep `device_class: energy`. Current day, month and year values, "Energiemenge HZ/WW/Kühl." and operating hours stay `total_increasing`. See the statistics note below.
- **No `unknown` after start.** The integration polls once right after setup. Before, values the parameter description does not carry, for example "Verdichterfrequenz", stayed `unknown` for one poll interval.

### Changed

- **Device assignment.** Devices come only from data that names them: the expert submenu, the device schema configuration or `ProtGrp` ([ADR-Model-010](docs/adr/ADR-Model-010-device-assignment-from-data-evidence.md)). The overview schema ports move to the heat generator or the mixer module. The user-level controls for heating and DHW, including "1x Warmwasser", stay on the system device, because no data names a module for them ([discovery, sections 12 and 13](docs/discovery.md)). Entity IDs, unique IDs and history are unchanged; only the device changes.
- **Overview schema ports show text values.** "Mischermotor" shows Aus/Zu/Auf and "Ausgang MKP" Aus/Ein instead of raw numbers; list items and units come from the device schema configuration. Their names change from "Mischermotor MM" and "MKP Mischerkreispumpe" to the Wolf labels "Mischermotor" and "Ausgang MKP".
- **Names.** All entities use the Wolf labels ([ADR-Model-011](docs/adr/ADR-Model-011-parameter-model-entity-mapping-and-naming.md)). "One-time DHW charge" is now "1x Warmwasser"; its entity ID `switch.<system>_one_time_dhw_charge` stays. Labels are unique per system, so a few friendly names gain a suffix, for example "Außentemperatur (Heizung)". No entity ID changes.
- **Entities disabled by default** for new installations. Complete list for the recorded heat pump with BM-2 and MM1, checked by `tests/test_real_fixtures.py::test_disabled_by_default_on_new_installation`:
  - all 168 parameters from the expert menu ("Fachmann"), as before;
  - "Ausgang MKP": overview schema port that duplicates the tab parameter "Mischerkreispumpe", which stays enabled;
  - statistics that need an S0 electricity meter: "Verbrauch Vortag", "Verbrauch aktueller Monat", "Verbrauch aktuelles Jahr", "Verbrauch Vorjahr", "Verbrauch Vorvorjahr", "TAZ Vortag", "MAZ aktueller Monat", "JAZ aktuelles Jahr", "JAZ Vorjahr", "JAZ Vorvorjahr";
  - "Raumtemperatur" (only with a room sensor).

  "Verdichterfrequenz" and "Mischermotor" stay enabled. Other installations follow the same rules ([README](README.md#entities-disabled-by-default)).

### Upgrade notes

**Entities that are now disabled by default.** Home Assistant applies "disabled by default" only when an entity is created. On installations that ran 0.1.0, these entities stay enabled:

- Ausgang MKP (formerly "MKP Mischerkreispumpe")
- Verbrauch aktueller Monat, Verbrauch aktuelles Jahr, Verbrauch Vortag, Verbrauch Vorjahr, Verbrauch Vorvorjahr
- JAZ aktuelles Jahr, JAZ Vorjahr, JAZ Vorvorjahr, MAZ aktueller Monat, TAZ Vortag
- Raumtemperatur

Removing and re-adding the integration does **not** change this. Home Assistant keeps deleted registry entries for 30 days and restores their settings, including "enabled", when the same entity comes back. Disable the ones without data by hand under Settings › Devices & services › Wolf SmartSet › Entities.

**Orphaned registry entries: none expected, no cleanup built in.** This release removes no entity. Schema ports and meter statistics are only disabled by default, not filtered out, so every unique ID from 0.1.0 is still provided. We therefore did not add an automatic registry cleanup. Deleting registry entries automatically could also remove entities a user still references, if a parameter disappears only temporarily from Wolf's description. Should a future Wolf change remove parameters, Home Assistant marks those entities as "no longer provided", and you can delete them in the entity settings. We will revisit automatic cleanup (Quality Scale rule `stale-devices`) if that happens.

**Statistics of the six closed-period sensors.** Their long-term statistics recorded so far are wrong, because Home Assistant summed every drop as a reset. After the update, Home Assistant reports "*sensor.… Verfügt nicht mehr über eine Zustandsklasse*" ("*… no longer has a state class*") for each of them under Settings › Repairs. That entry cannot be fixed from the repairs page. To clean up:

1. Open Developer tools › Statistics.
2. Search for the affected sensor, for example `vortag` or `vorjahr`.
3. The row shows the issue. Select **Fix issue** and confirm deleting the long-term statistics of that sensor.

Home Assistant then stops collecting long-term statistics for these sensors, because energy sensors without a state class have none. The normal state history remains (by default 10 days). If you want to keep the old numbers anyway, export them before deleting. They are not correct as sums.

# Changelog

## Unreleased (planned as 0.2.0)

### Fixed

- **No more Home Assistant warnings at setup.** The integration uses its own HTTP client and closes only that one. Sub-devices link to the system device through `via_device_id`; `via_device` stops working in Home Assistant 2027.8.
- **State class of closed-period energy values.** Sensors for a closed period no longer use `total_increasing`, because their value can drop. Home Assistant read every drop as a meter reset and added the new value to the long-term sum. Affected: "Verbrauch Vortag", "Erzeugte Wärmemenge Vortag", "Verbrauch Vorjahr", "Erzeugte Wärmemenge Vorjahr", "Verbrauch Vorvorjahr", "Erzeugte Wärmemenge Vorvorjahr". They keep `device_class: energy`. Current day, month and year values, "Energiemenge HZ/WW/Kühl." and operating hours stay `total_increasing`. See the statistics note below.
- **No `unknown` after start.** The integration polls once right after setup. Before, values the parameter description does not carry, for example "Verdichterfrequenz", stayed `unknown` for one poll interval.

### Changed

- **Device assignment.** Parameters without an expert submenu now get the device of their ValueId prefix when every other parameter with that prefix sits on the same device ([ADR-Model-009](docs/adr/ADR-Model-009-device-assignment-with-value-id-prefixes.md)). "Programmwahl (Heizung)", "Sollwertkorrektur" and "1x Warmwasser" move to the BM-2. The overview schema ports move to the heat generator or the mixer module. The DHW parameters stay on the system device, because neither the prefixes nor the schema data name a device for them ([discovery, section 12](docs/discovery.md)). Entity IDs, unique IDs and history are unchanged; only the device changes.
- **Names.** All entities use the Wolf labels ([ADR-Model-008](docs/adr/ADR-Model-008-parameter-model-entity-mapping-and-naming.md)). "One-time DHW charge" is now "1x Warmwasser"; its entity ID `switch.<system>_one_time_dhw_charge` stays. Labels are unique per system, so a few friendly names gain a suffix, for example "Außentemperatur (Heizung)". No entity ID changes.
- **Entities disabled by default** for new installations: overview schema ports, statistics that need an S0 electricity meter, and "Raumtemperatur" (see [README](README.md#entities-disabled-by-default)).

### Upgrade notes

**Entities that are now disabled by default.** Home Assistant applies "disabled by default" only when an entity is created. On installations that ran 0.1.0, these entities stay enabled:

- Verdichterfrequenz, MKP Mischerkreispumpe, Mischermotor MM
- Verbrauch aktueller Monat, Verbrauch aktuelles Jahr, Verbrauch Vortag, Verbrauch Vorjahr, Verbrauch Vorvorjahr
- JAZ aktuelles Jahr, JAZ Vorjahr, JAZ Vorvorjahr, MAZ aktueller Monat, TAZ Vortag
- Raumtemperatur

Recommendation: disable the ones without data under Settings › Devices & services › Wolf SmartSet › Entities, or remove and re-add the integration. Re-adding deletes the integration's entities and devices together with their history.

**Orphaned registry entries: none expected, no cleanup built in.** This release removes no entity. Schema ports and meter statistics are only disabled by default, not filtered out, so every unique ID from 0.1.0 is still provided. We therefore did not add an automatic registry cleanup. Deleting registry entries automatically could also remove entities a user still references, if a parameter disappears only temporarily from Wolf's description. Should a future Wolf change remove parameters, Home Assistant marks those entities as "no longer provided", and you can delete them in the entity settings. We will revisit automatic cleanup (Quality Scale rule `stale-devices`) if that happens.

**Statistics of the six closed-period sensors.** Their long-term statistics recorded so far are wrong, because Home Assistant summed every drop as a reset. After the update, Home Assistant reports "*sensor.… Verfügt nicht mehr über eine Zustandsklasse*" ("*… no longer has a state class*") for each of them under Settings › Repairs. That entry cannot be fixed from the repairs page. To clean up:

1. Open Developer tools › Statistics.
2. Search for the affected sensor, for example `vortag` or `vorjahr`.
3. The row shows the issue. Select **Fix issue** and confirm deleting the long-term statistics of that sensor.

Home Assistant then stops collecting long-term statistics for these sensors, because energy sensors without a state class have none. The normal state history remains (by default 10 days). If you want to keep the old numbers anyway, export them before deleting. They are not correct as sums.

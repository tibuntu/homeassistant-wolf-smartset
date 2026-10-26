# ADR-Model-016: Stable translation keys for curated parameters

## Status

Accepted. Amends rule 1 of [ADR-Model-011](ADR-Model-011-parameter-model-entity-mapping-and-naming.md).

## Date

2026-10-26

## Context

ADR-Model-011 names every parameter entity with its Wolf label and uses no translation keys. Entity IDs are therefore derived from German labels and from device names, and they differ between installations and languages. External tools, in particular the `wolf` preset of the Heat Pump Hydraulic Card, need a way to find "the outside temperature of the heat generator" that does not depend on entity ID, device name or language. Home Assistant's `translation_key` on the entity registry entry is that mechanism.

The key has to be derived from a feature of the parameter that is identical across installations. Candidates were the `ValueId`, the `ParameterId` and the German `Name`.

Evidence from the two available descriptions, the wolf-comm example installation (`parameters-examples/heatpumpparameter.json`, another owner's CHA with BM-2 and MM1) and the owner's own installation:

- `ParameterId` equals `ValueId` for every one of the 225 mapped parameters in both descriptions.
- Both descriptions contain the same 288 parameters with the same IDs, names, groups and devices. Nothing in them is numbered per installation.
- The IDs carry the device template and the instance: prefix 27 is the heat generator, 36 the mixer circuit of the BM-2, 4 the mixer module, 35 the DHW system, 22 the BM-2 system parameters; the last digits are 00001 for bus-addressed instances and 00000 for singletons (compare ADR-Model-009).
- The core `wolflink` integration builds its unique IDs from the same `ParameterId`, and this integration's unique IDs are `<system_id>_<parameter_id>` already.
- Names are German in the API regardless of the login language (`docs/discovery.md`); wolf-comm translates them client-side. Names carry prefixes ("MI72 …", "WP025 …") and repeat ("Programmwahl" twice), so a name-based table would need the same disambiguation the labels need.

## Decision

1. A curated table `translation_keys.py` maps `ParameterId` to a key per platform (`sensor`, `number`, `select`, `switch`). The key applies only when the parameter maps to that platform; otherwise the entity keeps the Wolf label and has no key.
2. Keys are English `snake_case`. Where the core `wolflink` integration exposes the same value, the key uses its entity-ID suffix (`outside_temperature`, `3_way_diverter_valve_htg_dhw`, …) so a card preset can serve both integrations. Values that exist per heating circuit get a circuit suffix (`day_temperature_mixer_circuit_1`).
3. Keyed entities drop the name attribute and are named through `strings.json` and `translations/`. The German name is the label the entity showed before, so nothing changes on German systems. English systems show English names for keyed entities and Wolf labels for the rest.
4. State values stay as Wolf delivers them. No `state` translations in this release; changing states would break dashboards and automations.
5. The table is a public interface documented in the README. Keys are only added, never renamed or reassigned. New device families or a second mixer circuit get new rows.

## Rationale

The `ParameterId` is the identity the integration already uses for unique IDs and polling, it is language-independent, and the two independent installations agree on all of it. The German label still carries the installation-specific disambiguation suffixes of ADR-Model-011 ("Außentemperatur (Heizung)"), which a name table would have to reproduce.

Mixed naming on English systems, the reason ADR-Model-011 rejected translation keys, is accepted for the curated set: these entities are the ones users build dashboards on, and the key is the point of the feature, the English name a side effect.

### Alternatives Considered

**Key by German name with a curated table**

- Pro: would also match the same label on other Wolf device families without new rows.
- Con: a name is not unique ("Programmwahl", "Tagtemperatur (Heizung)"), the same name on a second module would produce a duplicate key, and a renamed label silently loses the key.

**Keep the name attribute and only set the key**

- Pro: no visible change anywhere.
- Con: the name attribute wins over the translation, so `strings.json` names would be dead text and hassfest would still require them.

**Translate states as well**

- Pro: English state values on English systems.
- Con: breaking change for every automation and dashboard comparing against "Heizbetrieb" or "Ein".

## Consequences

### Positive

- Cards and templates can address curated entities by key on any installation and in any language.
- Existing entity IDs, unique IDs and German names are unchanged; the registry picks up the key on the next start.

### Negative

- Fresh installations in English get English entity IDs for keyed entities and German ones for the rest.
- The table covers one device family. Other Wolf systems need rows added from their descriptions.

### Risks

- If Wolf ever renumbers IDs, the keys disappear instead of moving. The fixture test pins every row to its parameter and label, so such a change shows up in the test suite before a release.

## Related Decisions

- [ADR-Model-011: Parameter model, entity mapping and naming (revision 3)](ADR-Model-011-parameter-model-entity-mapping-and-naming.md) — rule 1 amended by this ADR
- [ADR-Model-009: Device assignment with ValueId prefixes](ADR-Model-009-device-assignment-with-value-id-prefixes.md) — analysis of the ID structure
- [ADR-Model-010: Device assignment from data evidence only](ADR-Model-010-device-assignment-from-data-evidence.md)

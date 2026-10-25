# ADR-Model-011: Parameter model, entity mapping and naming (revision 3)

## Status

Accepted

## Date

2026-10-25

## Context

This ADR supersedes ADR-Model-008, which itself superseded ADR-Model-002. It restates ADR-Model-008 and changes how overview schema ports are handled. The rest of this context is unchanged from ADR-Model-008.

**Change in revision 3.** The review of the next build found that the schema ports still showed raw values ("MKP Mischerkreispumpe" `1`, "Mischermotor MM" `0`), and that disabling every schema-only port also hid "Verdichterfrequenz", which has no other source. The device schema configuration (`SchemaTabViewConfigDTO`, see ADR-Model-010) repeats each port with its list items, for example "Aus/Ein" and "Aus/Zu/Auf", its unit and its port text: `PortDesc` "MKP Mischerkreispumpe" is the port name "MKP" plus the name of the tab parameter "Mischerkreispumpe" (4007000001).

Original context of ADR-Model-008: the model and platform mapping of ADR-Model-002 held up against the owner's real installation: the parsed model of the recorded description is identical to the test fixture, and min, max, step and options come out right (review of v0.1.0, 2026-10-25).

The review of the running v0.1.0 found four problems in the mapping itself:

1. **Naming was inconsistent.** ADR-Model-002 gave known parameters an English translation key. In practice this produced "One-time DHW charge" next to about 50 German Wolf labels such as "Warmwassersolltemperatur eingestellt".
2. **Snapshot energy values used `total_increasing`.** "Verbrauch Vortag", "Erzeugte Wärmemenge Vorjahr" and similar values describe a closed period and can be lower than the previous value. Home Assistant reads every drop of a `total_increasing` sensor as a meter reset and adds the new value to the long-term sum.
3. **Overview schema entries without values at startup.** "Verdichterfrequenz", "MKP Mischerkreispumpe" and "Mischermotor MM" exist only as ports of the overview schema (`ControlType` 0 in every occurrence). The description carries no value for them, so they stayed `unknown` until the first poll two minutes after setup. Some duplicate a tab parameter under another `ValueId` ("MKP Mischerkreispumpe" 4000100001 versus "Mischerkreispumpe" 4007000001), so they cannot be merged by ID.
4. **Values without data basis.** "Verbrauch …", JAZ, TAZ and MAZ stay 0 when no S0 electricity meter is connected (WP110). "Raumtemperatur" never has a value without a room sensor. The description offers no generic signal for either case: none of these descriptors has a `ClientChooseCondition`, and WP110 holds its default pulse weight of 1000 whether a meter exists or not.

## Decision

The model rules of ADR-Model-002 stay as they were:

- Parameters are keyed by `ParameterId` and keep all their occurrences.
- Placeholders and hidden duplicates (`ValueId <= 0`, `ParameterId <= 0`, `NoDataPoint`, `ControlType` 31) are skipped.
- **New in revision 3:** entries of the schema configuration are read as additional occurrences. They supply list items, unit and `ProtGrp`, are always read-only, and lose to tab descriptors when both describe a parameter. A schema port therefore becomes an enum sensor with display texts instead of a raw number.
- **Writable** means the system's `AccessLevel` allows it, at least one occurrence has `IsReadOnly: false`, and that occurrence's `ControlType` is 1, 6 or 35.
- Platforms: `number` for writable numeric inputs with valid limits, `select` for writable lists, `sensor` (numeric, enum or diagnostic text) for everything read-only, `binary_sensor` for checkboxes. Dates, times, time programs and timed functions stay unmapped. `climate` and `water_heater` stay out of scope.
- Known one-time actions get a `switch` through a table keyed by `ParameterId`. It currently holds only "1x Warmwasser". The table only changes the platform and never makes a parameter writable.

Changes against ADR-Model-002:

1. **Naming: Wolf labels throughout.** Every entity, including known parameters, uses the label from the description: `NamePrefix` plus `Name`, for example "WP025 SG/PV". Labels must be unique per system, not just per device. Duplicates get the tab, then the group, then the `ParameterId` appended, for example "Programmwahl (Heizung)" and "Programmwahl (Warmwasser)". We use no translation keys for parameter entities.
2. **Read bundle.** Writable parameters are read and written through the bundle of their writable occurrence. Read-only parameters are read through a user-level occurrence's bundle when one exists, so enabled user-level entities never poll expert bundles.
3. **State class.** Energy and operating-hour sensors are `total_increasing` unless the name marks a closed period (`Vortag`, `Vormonat`, `Vorjahr`, `Vorvorjahr`). Those get no state class and keep their device class. Values of the current day, month or year stay `total_increasing`, because they only drop at the start of a new period, which Home Assistant handles as a reset.
4. **Disabled by default.** The following entities start disabled; users enable what applies to their installation:
   - expert-level parameters (unchanged);
   - **changed in revision 3:** schema ports that duplicate a tab parameter, that is ports whose `PortDesc` without the port name equals the name of another parameter with a tab descriptor (for example "Ausgang MKP" duplicates "Mischerkreispumpe"). Schema ports without such a twin, for example "Verdichterfrequenz" and "Mischermotor", stay enabled;
   - statistics that need an external electricity meter: names starting with "Verbrauch", "JAZ", "TAZ" or "MAZ";
   - optional sensor inputs: "Raumtemperatur";
   - diagnostic text values such as IP or MAC address (unchanged).
5. **Startup poll.** Right after the platforms are set up, every coordinator polls once. Values the description does not carry are therefore available immediately instead of after one interval.

## Rationale

German Wolf labels match the SmartSet app, the portal, the installation manual and the parameter numbers installers use. A curated translation for a single entity creates exactly the inconsistency the review found. Translating several hundred device-specific labels is out of reach, and a later Core submission can add translation keys for curated entities on top of this rule.

Changing a name never changes an existing `entity_id`, because the entity registry keeps it. The rename from "One-time DHW charge" to "1x Warmwasser" is therefore not breaking.

The rules for default enablement are name-based or structural, never tied to this installation's `ParameterId`s. A data-driven rule that would detect "always 0" or "never a value" at runtime would toggle the registry after setup, which Home Assistant does not do for integrations, and it would hide legitimate zero values.

### Alternatives Considered

**Translations (de, en) for curated entities, Wolf labels as fallback**

- Pro: proper English names for the important entities; the Core-preferred pattern.
- Con: two naming styles side by side on every device; needs a curated list per device family; German users gain nothing.

**Detect missing data at runtime and disable automatically**

- Pro: no name rules.
- Con: registry changes after setup; zeros are valid for many values; meter-less installations and summer months look the same.

**Filter schema-only parameters out entirely**

- Pro: no duplicates at all.
- Con: drops the only source of some values, for example "Verdichterfrequenz"; leaves orphaned registry entries on existing installations.

**Disable every schema-only port (revision 2)**

- Pro: simple structural rule.
- Con: also hides ports without a twin; did not fix the raw values.

## Consequences

### Positive

- One naming style, consistent with the Wolf app and documentation.
- Long-term statistics of snapshot values stay correct from now on.
- New installations start with only meaningful entities enabled.

### Negative

- Friendly names of a few existing entities change. Their `entity_id`s stay unchanged.
- `entity_registry_enabled_default` only applies to newly created entities. On installations that already ran v0.1.0, the affected entities stay enabled until the user disables them.
- Statistics already recorded with `total_increasing` for snapshot sensors remain wrong until the user fixes them in the developer tools (statistics tab). The changelog explains this.

### Risks

- The name patterns depend on Wolf's German labels. If Wolf renames them, a snapshot sensor could become `total_increasing` again. Unit tests pin the expected classes for all known labels.

## Related Decisions

- [ADR-Model-008: Parameter model, entity mapping and naming (revision 2)](ADR-Model-008-parameter-model-entity-mapping-and-naming.md) — superseded by this ADR
- [ADR-Model-010: Device assignment from data evidence only](ADR-Model-010-device-assignment-from-data-evidence.md)
- [ADR-Polling-003: Polling strategy](ADR-Polling-003-polling-strategy.md)

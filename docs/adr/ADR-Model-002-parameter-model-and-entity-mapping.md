# ADR-Model-002: Parameter model and entity mapping

## Status

Proposed

## Date

2026-10-25

## Context

`GetGuiDescriptionForGateway` returns the SmartSet GUI as a tree: menus "Benutzer" (user) and "Fachmann" (expert), tabs with a `BundleId`, and `ParameterDescriptors` (discovery, section 4). The heat-pump example has 529 descriptors, and the owner's installation is the same device family (CHA heat pump).

Facts that drive the model:

- The same parameter appears in up to three tabs. In 16 of 63 duplicate groups the `IsReadOnly` flag differs between occurrences, for example "Sparfaktor" is writable under BM-2 settings (bundle 6300) and read-only under the mixer module (bundle 10000).
- `IsReadOnly: false` alone does not mean writable. Overview measurements (`ControlType` 0) carry it.
- `ControlType` is an official enum with 36 values, taken from the portal JavaScript. It distinguishes numeric input, list selection, time programs, hidden duplicates (31 `Client_NO_DISPLAY`) and more.
- `ValueId` equals `ParameterId` for every real data point in all examples. A 2021 report says ValueIds changed after a reconnect, so `ParameterId` is the stable identity.
- `ValueId 0`, `ParameterId -1` and `NoDataPoint: true` mark containers, not data points.
- Writable numeric parameters almost always carry min, max, step and decimals.
- The system's `AccessLevel` (0 none, 1 user read, 2 user write, 3 expert read, 4 expert write) limits what the account may change.
- Names come in German from the API. `NamePrefix` carries Wolf's own parameter number (for example `WP025`, `A12`).
- The owner has no expert password, so we never perform `ExpertLogin`. Whether expert-level writes succeed without it is unknown (discovery, section 4.9).

The core review of PR #128988 asked for entities with context instead of raw `value_id` services.

## Decision

We will build a parameter model keyed by `ParameterId` and map it onto entity platforms by `ControlType`.

**Model.** For each `ParameterId` we keep every occurrence (tab, `BundleId`, `IsExpertView`, `IsReadOnly`, `ControlType`) plus the descriptor fields name, prefix, group, unit, min, max, step, decimals, list items and current value. We skip descriptors with `ValueId <= 0`, `ParameterId <= 0` or `NoDataPoint: true`. We also descend into `ChildParameterDescriptors`, so their parameters are known, but they stay unmapped in the MVP.

**Writable** means all three conditions hold:

1. The system's `AccessLevel` is at least 2 for user-level parameters and at least 4 for expert-level parameters.
2. At least one occurrence has `IsReadOnly: false`.
3. That occurrence's `ControlType` is in the writable set {1, 6, 35}.

For reads and writes we use the `BundleId` of the writable occurrence. A parameter counts as expert-level when all its occurrences sit in `IsExpertView: true` tabs.

**Platforms in the MVP:**

| ControlType | Writable | Read-only |
|---|---|---|
| 6 NumericInput | `number` (box mode, min/max/step from the description) | `sensor` |
| 1 ComboBoxText, 35 ProgramSelectionListView | `select` (options = selectable `ListItems`) | `sensor` (enum) |
| 0 ComboBoxImageText | never | `sensor` |
| 5 CheckBox | later | `binary_sensor` |
| 15, 16 solar statistics | never | `sensor` (energy) |
| 20, 21 text / IP | never | diagnostic `sensor`, disabled |
| 31 Client_NO_DISPLAY | skipped | skipped |
| 9, 10, 13, 14, 19, 24 dates, times, time programs, timed functions | later | later |

`switch` and `button` are reserved for one-time actions. We will not guess these from the generic description. A small table of known parameters, keyed by `ParameterId`, overrides the generic mapping. It starts with "1x Warmwasser" (`22004200000`, a switch: on starts a one-hour charge, off cancels it) and adds translation keys and device classes for the use-case parameters (DHW setpoint, operating mode, Sparfaktor, heating curve). The table only adds context. It never makes a parameter writable that the rules above reject.

**Naming and IDs.** The entity name is the API name with `NamePrefix` in front when present. When names repeat within a device we add the group. Known parameters use translation keys instead. The unique ID is `<system_id>_<parameter_id>`. Units the generic mapping does not know become a plain sensor with the raw unit string instead of being dropped.

**Defaults.** Expert-level entities are disabled by default. Writable parameters get `EntityCategory.CONFIG`, except the known use-case parameters, which stay primary entities. `climate` and `water_heater` entities are explicitly out of scope until the generic platforms work on the owner's system.

## Rationale

Keying by `ParameterId` and keeping all occurrences fixes the lossy deduplication that hides writable variants (wolf-comm) and avoids the first-occurrence rule that picks the user-level variant (ioBroker). Requiring `ControlType` as well as `IsReadOnly` keeps measurements from showing up as editable numbers. `AccessLevel` makes shared, read-only systems behave correctly.

A small known-parameter table answers the Core review: the use cases get proper context, while the generic mapping still covers the remaining few hundred parameters without hand-written descriptions.

### Alternatives Considered

**Writable means `!IsReadOnly` (ioBroker, heatwrite)**

- Pro: simple; matches what other projects do.
- Con: overview measurements become editable; contradictory duplicates resolved by order.

**Hand-curated entity descriptions only (typical core style)**

- Pro: best UX and translations.
- Con: covers only parameters we know; device families differ; heavy maintenance.

**`climate` / `water_heater` entities right away**

- Pro: best UX for heating and DHW.
- Con: needs a stable mapping of setpoints, modes and current temperatures across device families; we do not know enough yet.

## Consequences

### Positive

- Correct writability across duplicates and access levels.
- No parameter silently dropped; units preserved.
- Use cases get translated, contextual entities.

### Negative

- Entity names of generic parameters stay German.
- The known-parameter table needs maintenance per device family.

### Risks

- Expert-level writes may be rejected without `ExpertLogin`. Those entities are disabled by default, and ADR-Writes-004 covers rejected writes.
- The writable `ControlType` set is derived from four example systems. We validate it against the owner's real description in Phase 2.

## Related Decisions

- [ADR-Client-001: Own thin API client](ADR-Client-001-own-thin-api-client.md)
- [ADR-Writes-004: Write confirmation and rejected writes](ADR-Writes-004-write-confirmation-and-rejected-writes.md)
- [ADR-Model-006: Device model](ADR-Model-006-device-per-wolf-device.md)

# ADR-Model-007: One HA device per expert submenu

## Status

Superseded by [ADR-Model-009](ADR-Model-009-device-assignment-with-value-id-prefixes.md)

## Date

2026-10-25

## Context

ADR-Model-006 decided on one HA device per Wolf device, keyed by bus type and index taken from `ProtGrp` (for example `HG <1>`) or from `SVGHeatingSchemaConfigDevices`. This ADR supersedes it.

Checking the example descriptions while starting Phase 2 showed that this key is not available where we need it:

- `ProtGrp` is present on only 161 of 529 descriptors in the heat-pump example and 153 of 442 in the gas example.
- Whole expert tabs have no `ProtGrp` at all, for example "Parameter HG" (69 descriptors), "Parameter" of the BM-2 (16) and the ISM tab (14).
- Where it exists, it often names a heating circuit rather than a module: `MK <1>` (mixer circuit) appears in the BM-2 tab and in the mixer-module tab, `DHK <0>` (direct circuit) in the BM-2 and heat-generator tabs.
- Matching `SVGHeatingSchemaConfigDevices` entries (`HG 1 CHA`, `BM 0 BM_2`, `MM 1 MM`) to tabs would need name heuristics.

The expert menu, in contrast, has exactly one submenu per physical module ("Heizgerät", "Bedienmodul BM-2 0", "Mischermodul MM1", "Solarmodul SM1", "ISM"), and every expert tab sits in one of them.

## Decision

We will create one HA device per SmartSet system and one child device per expert submenu, linked with `via_device` to the system device.

- **Device key:** the submenu name, slugified, for example `heizgerat`, `bedienmodul_bm_2_0`. The device identifier is `(wolf_smartset, "<system_id>_<device_key>")`. The device name is the submenu name.
- **Parameter assignment**, first match wins:
  1. the submenu under which the same `ParameterId` appears;
  2. the submenu most often associated with the parameter's `ProtGrp` elsewhere in the description;
  3. otherwise the system device.
- The system device carries the gateway information and the integration's own diagnostic entities.

## Rationale

The submenu is the only grouping that covers every expert parameter and maps one to one to hardware. User-level parameters mostly reappear in an expert tab, so rule 1 assigns them. `ProtGrp` remains useful as a secondary hint for the rest.

The trade-off is the key: submenu names are German display texts, while ADR-Model-006 wanted a language-independent bus key. All examples deliver German names regardless of the login language, and a rename by Wolf would only re-create devices, not entities, because entity unique IDs do not contain the device key.

### Alternatives Considered

**Bus key from `ProtGrp` (ADR-Model-006)**

- Pro: language-independent; matches the bus topology.
- Con: missing on most descriptors and on whole tabs; mixes circuits and modules.

**One device per system (core `wolflink`)**

- Pro: no heuristics at all.
- Con: hundreds of entities on one device.

## Consequences

### Positive

- Every expert parameter lands on the module that owns it.
- No name matching against schema templates.

### Negative

- Device identifiers depend on Wolf's submenu names.
- User-level parameters that appear nowhere else stay on the system device.

### Risks

- A renamed submenu creates a new device and leaves an empty old one. Stale-device cleanup is a Gold-level task and stays out of scope for now.

## Related Decisions

- [ADR-Model-006: One HA device per Wolf device](ADR-Model-006-device-per-wolf-device.md) — superseded by this ADR
- [ADR-Model-002: Parameter model and entity mapping](ADR-Model-002-parameter-model-and-entity-mapping.md)
- [ADR-Model-009](ADR-Model-009-device-assignment-with-value-id-prefixes.md) — supersedes this ADR

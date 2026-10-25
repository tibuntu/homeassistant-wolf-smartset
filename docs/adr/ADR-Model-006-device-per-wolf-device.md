# ADR-Model-006: One HA device per Wolf device

## Status

Superseded by [ADR-Model-007](ADR-Model-007-device-per-expert-submenu.md)

## Date

2026-10-25

## Context

Core `wolflink` creates one device per SmartSet system and puts every entity under it. On a heat pump that mixes the heat generator, the control module, a mixer circuit, the DHW system and the gateway into one list of several hundred entities.

The description identifies the physical devices in three places (discovery, sections 4.1 and 4.2):

- The expert menu has one submenu per device, for example "Heizgerät", "Bedienmodul BM-2 0", "Mischermodul MM1", "ISM".
- `SVGHeatingSchemaConfigDevices` lists device type and bus index, for example `HG 1`, `BM 0`, `MM 1`, `MK 1`, `WWSystem 0`, with a template name such as `CHA` or `BM_2`.
- Many descriptors carry `ProtGrp`, for example `HG <1>`, naming the device the parameter belongs to.

User-level parameters often lack `ProtGrp`, but they reappear under a device submenu or belong to a group such as "250_Warmwasser" or "073_Mischerkreis 1". The owner's installation is a CHA heat pump with a Link home gateway; whether a BM-2 and an MM1 are present is still unknown.

## Decision

We will create one HA device per SmartSet system and one child device per Wolf device, linked with `via_device` to the system device.

- **Device key:** device type and bus index, for example `HG_1`, `BM_0`, `MM_1`, taken from `ProtGrp` or `SVGHeatingSchemaConfigDevices`. The device identifier is `(wolf_smartset, "<system_id>_<device_key>")`. Model and name come from the template name and the expert submenu name.
- **Parameter assignment**, first match wins:
  1. the parameter's own `ProtGrp`;
  2. the device submenu under which the same `ParameterId` appears;
  3. otherwise the system device.
- The system device carries the gateway information, the online state and the integration's diagnostic entities (last change, undo button).

## Rationale

Grouping by physical device matches how installers and the Wolf documentation think about the system, and it keeps each device page short. Using the bus key instead of submenu names keeps identifiers stable when Wolf renames menus or changes the session language. Falling back to the system device means no parameter is ever lost because the assignment is unclear.

### Alternatives Considered

**One device per system (core `wolflink`)**

- Pro: simple; same as core.
- Con: hundreds of entities on one device; no notion of which module a parameter belongs to.

**One device per tab**

- Pro: trivial to derive.
- Con: tabs are GUI groupings ("Übersicht", "Parameter HG"), not hardware; user-level tabs mix devices.

## Consequences

### Positive

- Device pages match the hardware; model information is visible.
- Stable identifiers independent of display language.

### Negative

- The assignment rules are heuristics. Some user-level parameters may land on the system device.

### Risks

- The bus key format has only been seen in four example descriptions. We validate it against the owner's description in Phase 2 and adjust before any entity IDs become permanent.

## Related Decisions

- [ADR-Integration-000: Standalone integration](ADR-Integration-000-standalone-integration.md)
- [ADR-Model-002: Parameter model and entity mapping](ADR-Model-002-parameter-model-and-entity-mapping.md)
- [ADR-Model-007: One HA device per expert submenu](ADR-Model-007-device-per-expert-submenu.md) — supersedes this ADR

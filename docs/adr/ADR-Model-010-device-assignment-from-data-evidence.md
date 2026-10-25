# ADR-Model-010: Device assignment from data evidence only

## Status

Accepted

## Date

2026-10-25

## Context

This ADR supersedes ADR-Model-009, which added a third assignment rule: a parameter without a submenu took the device of its `ValueId` prefix when all other parameters with that prefix sat on one device.

The review of the running build found the result inconsistent. "1x Warmwasser" (`22004200000`) landed on the BM-2 through prefix 22, while "Warmwassersolltemperatur eingestellt", "Programmwahl (Warmwasser)" and "Warmwasser Status" (prefix 35) stayed on the system device. The owner ruled that a prefix alone is not evidence: a parameter gets a device only from data that names it.

Checking for such data showed a better source we did not read before. Each expert tab with a device schema has `SchemaTabViewConfigDTO.Configs[].Parameters`: one entry per port of every hydraulic configuration, with `PortName`, `PortDesc`, `ProtGrp`, `Unit` and `ListItems`, but without `IsReadOnly`. On the owner's system these entries cover all overview schema ports: eleven ValueIds under "Heizgerät" (`ProtGrp` "HG <1>") and three under "Mischermodul MM1" ("MM <1>"). None of the DHW parameters, "1x Warmwasser", "Programmwahl (Heizung)", "Sollwertkorrektur" or "Mischerkreispumpe" appears in any schema configuration, expert submenu or `ProtGrp`. See [discovery, sections 12 and 13](../discovery.md).

## Decision

We will assign devices from data evidence only:

1. the expert submenu under which the same `ParameterId` appears, including entries of that submenu's schema configuration;
2. the submenu most often associated with the parameter's `ProtGrp` elsewhere in the description;
3. otherwise the system device.

The `ValueId` prefix rule of ADR-Model-009 is removed. Schema configuration entries count as occurrences for rule 1 and as metadata (list items, unit, `ProtGrp`), but never for writability.

Devices stay as in ADR-Model-007: one per expert submenu, keyed by the slugified submenu name. Unique IDs stay `<system_id>_<parameter_id>`, so a changed assignment moves the existing entity to another device without re-creating it.

## Rationale

Every remaining rule points at a place in the description that names the device. The schema configuration replaces the prefix rule for the overview ports, which were its main beneficiaries, with real evidence. The parameters that lose their device are exactly the ones the data does not place, and they end up together on the system device: the user-level controls for heating and DHW.

### Alternatives Considered

**Keep the prefix rule (ADR-Model-009)**

- Pro: more parameters on a module device.
- Con: a correlation, not evidence; split the DHW controls across two devices.

**Prefix rule except for single exceptions such as "1x Warmwasser"**

- Pro: keeps "Programmwahl (Heizung)" on the BM-2.
- Con: a special rule per parameter, exactly what we want to avoid.

## Consequences

### Positive

- Every device assignment can be traced to a field in the description.
- Heating and DHW user controls sit together on the system device.

### Negative

- "1x Warmwasser", "Programmwahl (Heizung)", "Sollwertkorrektur" and "Mischerkreispumpe" move back from module devices to the system device on installations that ran the previous build.

### Risks

- None beyond ADR-Model-007: a renamed submenu creates a new device.

## Related Decisions

- [ADR-Model-009: Device assignment with ValueId prefixes](ADR-Model-009-device-assignment-with-value-id-prefixes.md) — superseded by this ADR
- [ADR-Model-011: Parameter model, entity mapping and naming (revision 3)](ADR-Model-011-parameter-model-entity-mapping-and-naming.md)

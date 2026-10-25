# ADR-Model-009: Device assignment with ValueId prefixes

## Status

Superseded by [ADR-Model-010](ADR-Model-010-device-assignment-from-data-evidence.md)

## Date

2026-10-25

## Context

This ADR supersedes ADR-Model-007. That ADR created one HA device per expert submenu and assigned a parameter, in this order, to the submenu where its `ParameterId` appears, to the submenu most associated with its `ProtGrp`, or to the system device.

In the running v0.1.0, the most important user-level controls ended up on the system device ("Zuhause"), because they appear only in user tabs: Programmwahl Heizung and Warmwasser, Warmwassersolltemperatur eingestellt, Sollwertkorrektur, 1x Warmwasser and Warmwasser Status. The overview schema entries had no device either.

We analysed the owner's recorded description (288 parameters). The leading digits of a `ValueId` (`ValueId // 10^9`) correlate with the device:

| Prefix | Assigned by rules 1 and 2 | Unassigned | Meaning (bus template) |
|---|---|---|---|
| 4 | 10 × Mischermodul MM1 | 3 | mixer module `MM` |
| 19 | 14 × ISM | 0 | gateway |
| 22 | 23 × Bedienmodul BM-2 0 | 3 | BM-2 system parameters (A-parameters) |
| 27 | 152 × Heizgerät | 1 | heat generator `CHA` |
| 36 | 21 × Bedienmodul BM-2 0 | 3 | mixer circuit `MK_BM_2` |
| 35 | none | 4 | DHW system `WWSystem_BM_2` |
| 32, 33 | none | 54 | time programs, party and holiday dates (unmapped) |

Within every prefix that has assigned parameters, all of them sit on the same device. Prefix 35 has no assigned parameter at all. Its schema template name `WWSystem_BM_2` suggests the BM-2, but that is a name match, not data.

## Decision

We keep ADR-Model-007's devices (one per expert submenu, keyed by the slugified submenu name) and its first two assignment rules, and add a third:

1. the submenu under which the same `ParameterId` appears;
2. the submenu most often associated with the parameter's `ProtGrp`;
3. **new:** the device of the parameter's `ValueId` prefix, if at least three parameters with that prefix are assigned and all of them sit on the same device;
4. otherwise the system device.

Device assignment never affects unique IDs. An entity's unique ID stays `<system_id>_<parameter_id>`. A changed assignment moves the existing registry entry to the new device and keeps its `entity_id`.

## Rationale

Rule 3 uses only evidence from the same description and applies only where that evidence is unanimous. It moves Programmwahl Heizung, Sollwertkorrektur and 1x Warmwasser to the BM-2, the schema port "Verdichterfrequenz" to the heat generator and the mixer ports to MM1. The DHW parameters (prefix 35) stay on the system device, because no data supports any device. We prefer that gap over a name heuristic.

### Alternatives Considered

**Fixed prefix table (27 heat generator, 36 BM-2, …)**

- Pro: also covers prefix 35.
- Con: hard-coded per device family; wrong as soon as a cascade or another controller uses different prefixes.

**Schema template names (`WWSystem_BM_2` → BM-2)**

- Pro: covers the DHW system.
- Con: string matching between template names and submenu names; no second data point to confirm it.

## Consequences

### Positive

- The main user-level controls sit on the module that owns them.
- No entity is re-created; history and automations keep working.

### Negative

- The DHW controls stay on the system device.

### Risks

- A system with mixed prefixes would leave more parameters on the system device. That is the intended fallback.

## Related Decisions

- [ADR-Model-007: One HA device per expert submenu](ADR-Model-007-device-per-expert-submenu.md) — superseded by this ADR
- [ADR-Model-008: Parameter model, entity mapping and naming](ADR-Model-008-parameter-model-entity-mapping-and-naming.md)
- [ADR-Model-010](ADR-Model-010-device-assignment-from-data-evidence.md) — supersedes this ADR

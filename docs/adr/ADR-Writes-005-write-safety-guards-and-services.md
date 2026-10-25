# ADR-Writes-005: Write safety guards and services

## Status

Superseded by [ADR-Writes-012](ADR-Writes-012-write-pipeline.md)

## Date

2026-10-25

## Context

Every write ends up in the controller's non-volatile memory. Wolf does not publish write-cycle limits; the concern comes from the heatwrite author and is reasonable for any EEPROM-backed controller. One ioBroker user got IP-blocked by a script that wrote the same value on every trigger (discovery, section 11).

The owner's rules: no write to the real system without explicit approval; every write path has a dry run, on by default in development; no no-op writes; a rate limit; one write at a time.

heatwrite implements most of this well: read-only check, no-op detection, 20 writes per hour, one lock, persistent history, undo, snapshots and `dry_run` on services. The core review of PR #128988 rejected uncontextualized services that take raw `value_id`s.

## Decision

All writes, from entities and services alike, go through one write pipeline in this order:

1. **Writable check** per ADR-Model-002. Non-writable parameters raise `ServiceValidationError`. There is no `force` override.
2. **Validation** against min, max and step, or against the selectable list items.
3. **No-op check:** the normalized target equals the last read value, then nothing is sent and the history records "unchanged".
4. **Dry run:** a config entry option "Allow writes", default off. While off, the pipeline stops here, logs the would-be request and raises `ServiceValidationError` with the planned change. Services also accept `dry_run: true` per call. For development, writes stay disabled until the owner approves the first real write in Phase 3.
5. **Rate limit:** at most N writes per rolling hour per config entry, default 10, configurable from 1 to 60. Excess writes raise an error.
6. **Lock:** one `asyncio.Lock` per config entry around write and confirmation (ADR-Writes-004). Polling does not take this lock.
7. **History:** every attempt is stored through `homeassistant.helpers.storage.Store` with time, system, parameter, old value, new value, source, result and error. The last 200 entries are kept.

**Services** exist only for actions that are not a single entity:

- `wolf_smartset.undo` reverts the last N confirmed changes through the same pipeline.
- `wolf_smartset.snapshot_create` and `wolf_smartset.snapshot_restore` save and restore all writable parameters that have entities; restore takes a snapshot first.

All three accept `dry_run` and return a response with the planned or performed changes. Services are registered in `async_setup`. There is no generic `set_value` service.

A diagnostic sensor shows the last change, and a button "Undo last change" covers the common case without a service call.

## Rationale

A single pipeline makes the guarantees hold for every write path. A global "Allow writes" switch that defaults to off gives every new installation, including ours during development, a safe start; enabling it is a deliberate act. A lower default rate limit than heatwrite fits our use cases, a few writes per day for PV-driven DHW, and still catches loops quickly. Dropping `force` removes the only path that could write a parameter the API reports as read-only.

Restricting services to undo and snapshots follows the Core review: everything else is an entity with context.

### Alternatives Considered

**heatwrite's guards as they are, including `force` and `set_value`/`set_by_name` services**

- Pro: proven feature set; power users can write anything.
- Con: raw-ID services were rejected by Core; `force` bypasses the read-only flag.

**Dry run only as a per-call service flag**

- Pro: less configuration.
- Con: entity writes from the UI or automations have no dry run; does not satisfy the development default.

## Consequences

### Positive

- Every write is validated, deduplicated, rate-limited, serialized, confirmed and logged.
- New installations cannot write by accident.

### Negative

- Users must find and enable "Allow writes" before anything works. The README and the error message must point there.
- No escape hatch for parameters the API flags wrongly as read-only.

### Risks

- The no-op check relies on the last read value. If that value is stale, a needed write may be skipped. The confirmation read in ADR-Writes-004 and the poll keep the value fresh; undo bypasses the no-op check because it restores a known previous value.

## Related Decisions

- [ADR-Writes-004: Write confirmation](ADR-Writes-004-write-confirmation-and-rejected-writes.md)
- [ADR-Model-002: Parameter model and entity mapping](ADR-Model-002-parameter-model-and-entity-mapping.md)
- [ADR-Writes-012: Write pipeline](ADR-Writes-012-write-pipeline.md) — supersedes this ADR

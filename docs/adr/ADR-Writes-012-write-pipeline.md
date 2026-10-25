# ADR-Writes-012: Write pipeline with dry run, optimistic state and correction

## Status

Accepted

## Date

2026-10-25

## Context

This ADR supersedes ADR-Writes-004 (write confirmation by reading back for up to 60 s, no optimistic state) and ADR-Writes-005 (write safety guards and services). Both were accepted before the first build ran. The owner's review of that build (2026-10-25) set different requirements for Phase 3:

- no-op suppression: no API call when the parameter already has the target value;
- a rate limit with a default of 20 writes per hour, configurable in the options flow (ADR-Writes-005: 10);
- one write at a time (lock);
- validation against min, max, step and options before sending, and respecting `IsReadOnly`;
- **optimistic state, corrected by the next poll** if the controller rejects the value (ADR-Writes-004 rejected optimistic state);
- **dry run as an option in the options flow**: instead of a write, an INFO log line with parameter, old and new value (ADR-Writes-005: an "Allow writes" switch that raised an error);
- the last writes in the diagnostics, with result, persisted in `.storage`.

The original Phase 3 brief also asks for undo, and for services only where an entity does not fit, each with a dry run.

Facts that still hold: every write ends in the controller's EEPROM; the portal's own client confirms writes by polling for up to 60 s; a request that failed with a timeout or 5xx may have reached the controller anyway (discovery, section 5.2).

## Decision

Every write, from `number`, `select` and `switch` entities and from the undo button, runs through one pipeline per config entry (`write.py`):

1. **Writable check.** The parameter must be writable by the model rules (ADR-Model-011: `IsReadOnly` false and a writable `ControlType`) and the system's `AccessLevel` must allow it: at least 2 for user-level and 4 for expert-level parameters. Otherwise `ServiceValidationError`.
2. **Validation.** Numbers must lie within min and max and on the step grid from the minimum. List values must be a selectable list item. Otherwise `ServiceValidationError`; nothing is sent.
3. **Lock.** Steps 4 to 8 run under one `asyncio.Lock` per config entry. Polls do not take this lock.
4. **No-op.** If the last known value equals the target (numerically for numbers), nothing is sent. The history records `unchanged`.
5. **Dry run.** Option "Dry run", **default on**. While on, the pipeline logs `Dry run: would write <label> (ValueId <id>) <old> -> <new>` at INFO and records `dry_run`. Entity states do not change.
6. **Rate limit.** At most N real writes per rolling hour, option "Maximum writes per hour", default 20, range 1 to 60. No-ops and dry runs do not count. Exceeding it raises a translated `HomeAssistantError` and records `rate_limited`.
7. **Write.** `WriteParameterValues` with the portal's payload and the bundle of the writable occurrence. The client never retries a write, also not after HTTP 401 or 5xx. A failure raises `write_failed` and records `error`.
8. **Optimistic state.** After a successful response the entity shows the new value immediately.
9. **Correction.** The first poll that runs at least 30 s after the write compares the value. If it matches, the record is marked `confirmed`. If not, the polled value replaces the optimistic one, the record becomes `not_applied`, and a WARNING names parameter, written value and read-back value.

**History.** Every attempt (including no-ops, dry runs, rate-limited and failed writes) is stored in `.storage/wolf_smartset.<entry_id>.history`, last 200 entries, with time, parameter, value ID, label, old and new value, source and result. The diagnostics show the last 50 without system IDs.

**Undo.** A button entity "Undo last change" writes the old value of the latest applied, not yet undone change back through the same pipeline, so dry run, no-op check, rate limit and validation apply to it. It is unavailable while there is nothing to undo.

**Services.** None. Undo is an entity; the dry run is an option and applies to every write path. Snapshots (ADR-Writes-005) are dropped: neither the brief nor the review asks for them, and undo covers the realistic recovery case.

## Rationale

The owner's requirements trade certainty for responsiveness: the UI reacts immediately, and the next poll repairs a wrong display within one interval. The correction step keeps the honest part of ADR-Writes-004: a rejected write is visible in the log and in the history instead of disappearing silently. The 30 s guard avoids marking a write as rejected when a poll happens to run seconds after it, before the controller has applied the value.

A global dry-run option, on by default, makes every new installation and every development setup safe without depending on each caller remembering a flag. Writes that would not change anything never reach the controller, which matters more for the EEPROM than any rate limit.

### Alternatives Considered

**Confirmation by read-back before returning (ADR-Writes-004)**

- Pro: the UI never shows an unconfirmed value.
- Con: the action blocks for up to 60 s; up to 12 extra reads per write; not what the owner asked for.

**"Allow writes" switch that raises an error (ADR-Writes-005)**

- Pro: the user notices immediately that nothing was written.
- Con: automations fail instead of being rehearsed; the review asked for a log line.

**Undo and snapshot services**

- Pro: scriptable rollback of many parameters.
- Con: not requested; services without entity context are what the Core review discouraged.

## Consequences

### Positive

- One code path for every write; every safeguard has its own test.
- New installations cannot write by accident.
- Rejected writes become visible after the next poll.

### Negative

- For up to one poll interval the UI can show a value the controller did not accept.
- The user must switch the dry run off before anything is written. Automations "succeed" silently while it is on; the INFO log and the history show what would have happened.

### Risks

- The no-op check relies on the last polled value. If that value is stale, a needed write may be skipped. The default interval of 120 s and the startup poll keep it fresh.
- A write that timed out may have been applied. The history records `error`; the next poll shows the real value.

## Related Decisions

- [ADR-Writes-004: Write confirmation instead of optimistic state](ADR-Writes-004-write-confirmation-and-rejected-writes.md) — superseded by this ADR
- [ADR-Writes-005: Write safety guards and services](ADR-Writes-005-write-safety-guards-and-services.md) — superseded by this ADR
- [ADR-Model-011: Parameter model, entity mapping and naming](ADR-Model-011-parameter-model-entity-mapping-and-naming.md)

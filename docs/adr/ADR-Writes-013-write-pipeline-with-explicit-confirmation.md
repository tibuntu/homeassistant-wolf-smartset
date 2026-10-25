# ADR-Writes-013: Write pipeline with explicit confirmation

## Status

Accepted

## Date

2026-10-25

## Context

This ADR supersedes [ADR-Writes-012](ADR-Writes-012-write-pipeline.md). The first real writes on the owner's system (discovery, section 14) showed two gaps in its correction step:

- Switching "1x Warmwasser" off took about 17 s until the portal answered. A poll that started during the write returned the old value, and the switch showed "on" again until the next poll. Polls do not take the write lock, and a poll within 30 s of a write could overwrite the optimistic value. The no-op check then compares against the stale value.
- The history marked a confirmed write with `confirmed: true` and left the field out in every other case. A missing confirmation (still pending, poll failed, restart) could not be told apart from an old record.

The owner's review asked for explicit `confirmed: false` plus the read-back value.

## Decision

Steps 1 to 8, history, undo and services are unchanged from ADR-Writes-012. Steps 9 and 10 replace its correction step.

Every write, from `number`, `select` and `switch` entities and from the undo button, runs through one pipeline per config entry (`write.py`):

1. **Writable check.** The parameter must be writable by the model rules (ADR-Model-011: `IsReadOnly` false and a writable `ControlType`) and the system's `AccessLevel` must allow it: at least 2 for user-level and 4 for expert-level parameters. Otherwise `ServiceValidationError`.
2. **Validation.** Numbers must lie within min and max and on the step grid from the minimum. List values must be a selectable list item. Otherwise `ServiceValidationError`; nothing is sent.
3. **Lock.** Steps 4 to 8 run under one `asyncio.Lock` per config entry. Polls do not take this lock.
4. **No-op.** If the last known value equals the target (numerically for numbers), nothing is sent. The history records `unchanged`.
5. **Dry run.** Option "Dry run", **default on**. While on, the pipeline logs `Dry run: would write <label> (ValueId <id>) <old> -> <new>` at INFO and records `dry_run`. Entity states do not change.
6. **Rate limit.** At most N real writes per rolling hour, option "Maximum writes per hour", default 20, range 1 to 60. No-ops and dry runs do not count. Exceeding it raises a translated `HomeAssistantError` and records `rate_limited`.
7. **Write.** `WriteParameterValues` with the portal's payload and the bundle of the writable occurrence. The client never retries a write, also not after HTTP 401 or 5xx. A failure raises `write_failed` and records `error`.
8. **Optimistic state.** After a successful response the entity shows the new value immediately.
9. **Hold.** A successful poll that runs less than 30 s after the write, or that does not read the value, keeps the written value in the coordinator data. This also covers a poll that was already in flight while the write ran.
10. **Confirmation.** The first successful poll that reads the value at least 30 s after the write decides. Every applied write carries `confirmed` and `read_back`: `confirmed: null` while pending, `true` if the value matches, `false` if not. On `false` the polled value replaces the optimistic one, the result becomes `not_applied`, and a WARNING names parameter, written value and read-back value. A restart drops pending checks; those records become `confirmed: false` with `read_back: null`.

**History.** Every attempt (including no-ops, dry runs, rate-limited and failed writes) is stored in `.storage/wolf_smartset.<entry_id>.history`, last 200 entries, with time, parameter, value ID, label, old and new value, source and result. The diagnostics show the last 50 without system IDs.

**Undo.** A button entity "Undo last change" writes the old value of the latest applied, not yet undone change back through the same pipeline, so dry run, no-op check, rate limit and validation apply to it. It is unavailable while there is nothing to undo.

**Services.** None. Undo is an entity; the dry run is an option and applies to every write path. Snapshots (ADR-Writes-005) are dropped: neither the brief nor the review asks for them, and undo covers the realistic recovery case.

## Rationale

Holding the written value for 30 s makes the poll timing irrelevant: whether the poll started before, during or right after the write, the entity and the no-op check see the written value until a read that can actually reflect the controller's state. An explicit `confirmed` on every applied write makes the history auditable without knowing the code.

### Alternatives Considered

**Polls take the write lock**

- Pro: no poll can run during a write.
- Con: does not help for a poll right after the write, before the controller has applied the value; blocks polling for the duration of slow writes.

**Skip the poll result for written value IDs entirely until 30 s have passed**

- Pro: same effect.
- Con: needs the write manager inside the coordinator's poll; the listener approach keeps the coordinator free of write logic.

## Consequences

### Positive

- No flicker back to the old value after a slow write.
- Every applied write states whether it was confirmed and what was read back.

### Negative

- For up to 30 s, and longer if the value is not polled, a rejected value stays visible.

### Risks

- If a value is never polled again (entity disabled after the write), the record stays `confirmed: null` until the next restart, then becomes `false`.

## Related Decisions

- [ADR-Writes-012: Write pipeline with dry run, optimistic state and correction](ADR-Writes-012-write-pipeline.md) — superseded by this ADR
- [ADR-Model-011: Parameter model, entity mapping and naming](ADR-Model-011-parameter-model-entity-mapping-and-naming.md)

# ADR-Writes-018: Settle window before a write counts as not applied

## Status

Accepted

## Date

2026-11-21

## Context

[ADR-Writes-013](ADR-Writes-013-write-pipeline-with-explicit-confirmation.md), step 10, lets the first successful poll at least 30 s after a write decide: matching value confirmed, any other value `not_applied`.

A read-only measurement on the owner's system on 2026-11-18 (poll interval 120 s) showed that the portal reports some values minutes late. DHW setpoint ("Warmwassersolltemperatur eingestellt"):

- 13:00:00 UTC write 48 → 60, sent ok. 13:01:41 (about 100 s later) still read 48, so the record became `not_applied` and the entity snapped back to 48. 13:03:41 (about 220 s) read 60: the write had applied.
- 14:39:41 write 60 → 48. 14:41:41 (120 s) read 60, `not_applied` again. 14:43:41 (240 s) read 48.

The "1x Warmwasser" switch was confirmed on the first poll every time. The result was a false `not_applied` event and warning, and the entity showing the old value for one poll.

## Decision

This ADR replaces steps 9 and 10 of ADR-Writes-013 for the mismatch case; everything else there stays.

1. The first successful poll at least 30 s after the write that reads the written value confirms it (`confirmed: true`, event `confirmed`).
2. A different value is final only once the settle window has passed: `max(2 × poll interval, 300 s)`. Until then the written value stays in the coordinator data, so entities and the no-op check keep seeing it.
3. The first successful poll after the window that still reads another value records `not_applied` as before (`confirmed: false`, `read_back`, warning, event).
4. `confirmed` or `not_applied` fire exactly once per write. A newer write to the same parameter replaces the pending one; the replaced record keeps `confirmed: null` and fires neither. The history format and the restart behaviour are unchanged.

## Rationale

The latest confirmation measured came 240 s after the write. 300 s covers that with margin at the shortest allowed interval (60 s). Two intervals keep at least one more poll after a stale one in case the portal's delay is tied to polls rather than to time. At the default 120 s the window is 300 s, so a real rejection is reported on the third poll (about 6 minutes).

### Alternatives Considered

**Longer fixed `CONFIRM_AFTER_SECONDS`**

- Con: delays confirmation of every write, including the switch that reads back on the first poll.

**Only a fixed time (300 s)**

- Con: no second look if the delay grows with the poll interval.

## Consequences

- No false `not_applied` for values that reach the portal within the window.
- A write the controller really rejects shows the written value for up to one window plus one poll before it is corrected.

## Related Decisions

- [ADR-Writes-013: Write pipeline with explicit confirmation](ADR-Writes-013-write-pipeline-with-explicit-confirmation.md) — steps 9 and 10 amended by this ADR
- [ADR-Polling-003: Polling strategy](ADR-Polling-003-polling-strategy.md) — poll interval

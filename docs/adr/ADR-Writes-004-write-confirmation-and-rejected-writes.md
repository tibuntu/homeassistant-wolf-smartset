# ADR-Writes-004: Write confirmation instead of optimistic state

## Status

Proposed

## Date

2026-10-25

## Context

`WriteParameterValues` answers before the controller has applied the value. The official web portal marks the value as "write pending", polls the bundle every 3 s for up to 60 s and shows the value once it comes back with an OK state (`EnParamState`: ReadPending 0, OK 1, WritePending 2, WriteAcknowledge 3, Timeout 4, Error 5). See discovery, section 5.2.

heatwrite shows the new value optimistically and lets the next poll, up to five minutes later, correct it. `wolflink-write` expects feedback within one to two minutes. A write can fail in three ways:

1. The API returns an error code (for example `SystemOffline`, `InvalidSession`).
2. The request fails at HTTP level (timeout, 5xx), so we do not know whether the value arrived.
3. The API accepts the request but the controller keeps the old value, for example when the value is outside a dependent limit or an expert login is required.

Showing a value the heating system never accepted is misleading, and automations may act on it.

## Decision

We will confirm every write by reading the value back, the way the portal does, and we will not show optimistic state.

1. After a successful `WriteParameterValues` response, we read that parameter's bundle, restricted to the written `ValueId`, every 5 s for up to 60 s.
2. The write is confirmed when the read returns state OK and the written value. We then update the coordinator data and the entity.
3. When the time runs out, or the value comes back unchanged, or the state is Timeout or Error, the entity action raises a `HomeAssistantError` ("not confirmed by the controller"). The entity keeps showing the last read value, and the history records the write as unconfirmed.
4. API error codes raise immediately with a translated message. We do not retry.
5. HTTP failures during the write request are not retried either. We run the same confirmation read, because the value may have arrived, and report the outcome.
6. The write lock (ADR-Writes-005) is held until confirmation ends, so writes never overlap.

## Rationale

Read-back confirmation matches the official client, so it uses the API the way Wolf expects. The user sees either the confirmed value or an error, never a guess. Not retrying a write avoids duplicate EEPROM writes when the server applied the first attempt.

A 5 s interval with a 60 s limit costs at most 12 small reads per write. With the write rate limit from ADR-Writes-005 this stays far below the polling load.

### Alternatives Considered

**Optimistic state, corrected by the next poll (heatwrite)**

- Pro: instant UI feedback; simplest.
- Con: shows unconfirmed values for minutes; automations act on them; rejected writes are only noticed as a later jump back.

**Fire and forget, wait for the next poll**

- Pro: no extra requests.
- Con: no error reporting for rejected writes; stale UI for up to the poll interval.

**ioBroker's `parameters/write` endpoint, which returns values directly**

- Pro: confirmation in the response, no extra reads.
- Con: not used by the current official portal; we do not know whether the returned values reflect the controller or only the request. We test it once against the same harmless parameter in Phase 3 and supersede this ADR if it proves reliable.

## Consequences

### Positive

- Entity state always reflects what the controller reports.
- Rejected writes surface as clear errors and in the history.

### Negative

- A UI change takes up to 60 s to resolve, and the action blocks that long.
- Up to 12 extra reads per write.

### Risks

- Controllers that apply values later than 60 s would be reported as failures. We tune the timeout after the first real write in Phase 3.

## Related Decisions

- [ADR-Writes-005: Write safety guards and services](ADR-Writes-005-write-safety-guards-and-services.md)
- [ADR-Polling-003: Polling strategy](ADR-Polling-003-polling-strategy.md)

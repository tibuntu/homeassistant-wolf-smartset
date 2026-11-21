# ADR-Polling-019: Periodic ReadFaultMessages read for fault entities

## Status

Accepted

## Date

2026-11-21

## Context

Issue #25 asks for a `problem` binary sensor for faults. The parameter description has no verified fault signal ([ADR-Model-011](ADR-Model-011-parameter-model-entity-mapping-and-naming.md)). The portal's `ReadFaultMessages` endpoint has one: `CurrentMessages` lists the active faults, `HistoryMessages` the past ones, newest first (`docs/discovery.md`, sections 17.2 to 17.7; redacted recording `tests/fixtures/real/fault_messages.json`).

Facts from the portal JavaScript and the single approved recording of 2026-11-21:

- The browser sends `POST /portal/api/portal/ReadFaultMessages` with `{LastRead: null, GatewayId, SystemId}` every 10 s while a system is open, and starts this poll whenever a system is opened. It sends no `SessionId`; the recording without one answered HTTP 200.
- The call takes no `BundleId`, so the account lock seen after an invalid BundleId (discovery section 3.3) does not apply. Wolf blocks after too many logins, not after requests.
- Faults in the history lasted one to three minutes. `OccurTimeLocal` can be missing. A `CurrentMessages` entry has never been recorded; its shape is inferred from the portal's table columns and the history entries.

Rule 3 of the backlog lets the integration call only endpoints the owner approved.

## Decision

Owner decisions, chat 2026-11-21:

1. **Go for the periodic call.** One `POST /portal/api/portal/ReadFaultMessages` per system with exactly `{"LastRead": null, "GatewayId": <id>, "SystemId": <id>}`, using the existing access token. No new login beyond what the integration already does. `CommitFaultMessage` (acknowledges a fault at the controller) and every `…FaultMessageDestination…` endpoint (the account's e-mail notifications) stay off limits and are never called; a test guards the package against those names.
2. **Cadence: every 10 minutes, fixed**, not an option.
3. Reopening issue #25 is the owner's action.

Implementation:

- `WolfClient.read_fault_messages` sends the body above through `_call`, not `_request`: no `SessionId` is added and nothing is retried. It runs `_ensure_session` first, so an expired token is renewed through the existing login backoff (ADR-Client-014, ADR-Client-015) exactly as the next value poll would. A 401 raises without dropping the token, so a fault read that keeps failing never logs in by itself; the value poll stays the owner of token and session.
- A separate `WolfFaultCoordinator` per system with `update_interval` 10 minutes, next to the 120 s value coordinator. A failed read makes only its two entities unavailable. While the value coordinator backs off from throttling or a login block, the fault read is skipped and sends no request. The coordinator is tied to the config entry, so it stops on unload.
- Entities on the system device: binary sensor `fault` (device class `problem`, on while `CurrentMessages` is not empty) and sensor `fault_code` (`ErrorCode` of the first `CurrentMessages` entry, else `None`; attributes `description`, `occurred` and, from the first `HistoryMessages` entry, `last_fault_code`, `last_fault_description`, `last_fault_occurred`, `last_fault_ended`). Wolf's texts stay as sent (rule 6). No `Device`, `SystemName` or IDs in attributes (rule 2). New translation keys, additive ([ADR-Model-016](ADR-Model-016-stable-translation-keys.md)).
- Diagnostics include the last response per system through `redact_faults`.

## Rationale

**Why no `SessionId`.** It is the browser's request: the portal's `doRequest` adds none, and the approved recording without it worked. Whether the server tolerates an extra `SessionId` was never tested, and sending an untested payload on a periodic call is exactly what rule 3 avoids. The endpoint does not need the portal session, only the bearer token.

**Why 10 minutes.** One extra request per system and 10 minutes is small next to the value poll (several requests every 120 s) and far below the browser's 10 s. Short faults are not lost: the history entry keeps them, exposed as the `last_fault_*` attributes.

**Why a separate coordinator.** The value coordinator's availability drives every parameter entity; folding the fault read into it would let a failure of a secondary endpoint take them all down, and a different cadence would need its own timer anyway.

### Alternatives Considered

**Fault read inside the value poll**

- Con: a fault read failure marks all value entities unavailable; needs counting polls for the slower cadence.

**Through `_request` (with `SessionId` and one retry after 401)**

- Con: untested payload; a persistent 401 on this endpoint would log in again every 10 minutes.

**5-minute cadence or an option**

- Con: twice the requests without catching 1 to 3 minute faults either; the owner chose a fixed 10 minutes.

**An `event` entity for new history entries**

- Con: needs state across restarts to tell new entries from old ones. The `last_fault_*` attributes cover the need; revisit if automations need a trigger per fault.

## Consequences

- One additional request per system every 10 minutes; no additional login.
- A fault shorter than 10 minutes shows in the binary sensor only if a read happens to fall into it, but always in the `last_fault_*` attributes after the next read.
- The binary sensor builds only on "list not empty"; whether `Active` flips before an entry moves to the history is still open (discovery 17.6). The first real fault confirms or corrects the assumed entry shape.
- `SystemMaintenanceState` is in the diagnostics only; a maintenance sensor needs more evidence.

## Related Decisions

- [ADR-Polling-003: Polling strategy](ADR-Polling-003-polling-strategy.md) — the 120 s value poll, unchanged
- [ADR-Client-014: Login backoff](ADR-Client-014-login-backoff.md) and [ADR-Client-015](ADR-Client-015-login-backoff-survives-restarts.md) — the backoff the fault read goes through
- [ADR-Model-016: Stable translation keys](ADR-Model-016-stable-translation-keys.md) — keys `fault` and `fault_code` added

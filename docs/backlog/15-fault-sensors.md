# 15 – Fault sensors from ReadFaultMessages

Status: go given 2026-11-21 · Size: medium · Rules: [README](README.md#rules-for-every-brief)

## Owner decisions (chat, 2026-11-21)

1. **Go for the periodic call**: one `POST /portal/api/portal/ReadFaultMessages` with `{"LastRead": null, "GatewayId": <id>, "SystemId": <id>}` per system, without `SessionId`, using the existing access token. No new login beyond what the integration already does. `CommitFaultMessage` and every `…FaultMessageDestination…` endpoint stay off limits; never call them.
2. **Cadence**: every 10 minutes, fixed, not an option.
3. **Issue #25**: reopening is the owner's action later. Agents do not touch GitHub issues.

## Why

Issue #25 asks for a `problem` binary sensor for faults and maintenance. It was parked because the parameter description has no verified fault signal. The portal's fault-message endpoint has one: `ReadFaultMessages` returns the active faults (`CurrentMessages`) and a fault history (`HistoryMessages`). The owner approved one recording on 2026-11-21; facts and recommendation are in `docs/discovery.md`, sections 17.6 and 17.7, and the redacted response is `tests/fixtures/real/fault_messages.json`.

## Owner decisions needed first

1. **Go for a new periodic call.** The integration has never called `ReadFaultMessages` on its own (rule 3). Proposed: one `POST /portal/api/portal/ReadFaultMessages` with `{"LastRead": null, "GatewayId", "SystemId"}` per system every 5 to 10 minutes, without `SessionId` (as the browser and the recording did). No BundleId, no login. `CommitFaultMessage` and the `…FaultMessageDestination…` endpoints stay off limits.
2. **Cadence**: 5 or 10 minutes, and whether it is an option.
3. **Whether to reopen issue #25** (rule 8, the owner's action).

## What to build

- `binary_sensor`, device class `problem`, per system: on when `CurrentMessages` is not empty.
- `sensor` "fault code": the `ErrorCode` (integer) of the newest entry in `CurrentMessages`, `None` without one; attributes `description` (Wolf's text as sent, rule 6), `occurred` (`OccurTimeLocal`, may be missing).
- Both get new translation keys (additive, ADR-Model-016) and sit on the system device.
- A separate timer or coordinator for the slow cadence; the 120 s value poll stays unchanged. A failed fault read must not mark the value entities unavailable.
- Diagnostics: include the fault response through `redact_faults` (it blanks `SystemName` and `Device`).
- Tests against `tests/fixtures/real/fault_messages.json` plus a synthetic `CurrentMessages` entry.

## Evidence and unknowns

- **verified** (recording 2026-11-21): `ErrorCode` is an integer; `Description` is German display text; `OccurTimeLocal` can be missing; history covers about a year; no current fault at recording time.
- **inferred, not recorded**: the shape of a `CurrentMessages` entry (portal JS columns plus the history entries). Whether `Active` is `true` there and flips before the entry moves to the history. Build only on "list not empty" and the fields the history has, and tolerate missing ones.
- Faults in the history lasted 1 to 3 minutes, shorter than the proposed cadence. Optional: fire an `event` entity for new history entries (by `OccurTimeLocal`/`OutgoingTimeLocal` and `ErrorCode`), so short faults are not lost.
- `SystemMaintenanceState` (`Mode`, `Date`, `Progress`, `CWLFilterMaintenancePending`) is not understood well enough for a maintenance-due sensor. Out of scope; diagnostics only.

## Done when

The owner gave the go for the periodic call, both entities exist with translation keys, the fault read runs on its own cadence and failure path, tests cover empty and non-empty `CurrentMessages`, and an ADR records the cadence and the endpoint decision.

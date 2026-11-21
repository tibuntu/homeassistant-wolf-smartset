# ADR-Polling-020: The fault read never logs in

## Status

Accepted. Amends the client bullet of the implementation in [ADR-Polling-019](ADR-Polling-019-fault-messages-read.md) and its statement on the order of `CurrentMessages`.

## Date

2026-11-21

## Context

ADR-Polling-019 let `WolfClient.read_fault_messages` run `_ensure_session` first, so an expired token was renewed "exactly as the next value poll would". An independent review of 0.8.0 found that this is not true after an authentication failure:

- After a wrong or changed password, the value poll raises `ConfigEntryAuthFailed`. Home Assistant starts a reauth flow and stops scheduling that coordinator, so its `backoff_steps` stays 0.
- `AuthError` sets no login block (ADR-Client-015 exempts it, so the user can retry the password at once).
- The fault coordinator kept running every 10 minutes and its `_ensure_session` posted the wrong password each time, until the user finished reauth.

Before 0.8.0 nothing logged in after `ConfigEntryAuthFailed`. Repeated logins with a wrong password are what the portal locks accounts for. This broke the owner's condition for the endpoint: no new login beyond what the integration already does.

ADR-Polling-019 also stated in its context that both lists come newest first. Only the history has been recorded. No `CurrentMessages` entry has been recorded so far (`docs/discovery.md`, 17.6).

## Decision

1. `read_fault_messages` never logs in and never creates or refreshes a portal session. If there is no token, the token has expired, or there is no session, it raises `NoSession` and sends no request at all. Login, token and session belong to the value poll alone.
2. The fault coordinator also skips the read while Home Assistant reports an authentication problem: when the value coordinator's `last_exception` is `ConfigEntryAuthFailed`, or the config entry has an active reauth flow. The existing pause while the value poll backs off stays.
3. "Newest current fault = first `CurrentMessages` entry" is an assumption, taken over from the recorded history (Index 0 = newest). The first recorded real fault confirms or corrects it.

Unchanged from ADR-Polling-019: the payload without `SessionId`, the fixed 10-minute cadence, the immediate read at setup, the per-system pause and the entities.

## Rationale

The value poll runs every 120 s by default and renews token and session itself. So with the value poll healthy, the fault read always finds a valid token and session. When the value poll is not healthy (auth failure, login block, throttling), the fault read has no business sending anything. Point 1 on its own already stops the login loop. Point 2 also covers an auth failure that leaves the token valid, for example an `ErrorCode 3` answer, and a reauth flow the user dismissed while the value poll stays stopped.

### Alternatives Considered

**Keep `_ensure_session` and set a login block on `AuthError`**

- Con: ADR-Client-015 deliberately lets the user retry a corrected password at once. And the fault read would still log in on its own whenever the value poll is stopped.

**Only check the reauth flow**

- Con: a dismissed reauth flow would resume fault reads while the value poll stays stopped.

## Consequences

- No login, `CreateSession2` or `UpdateSession` request ever comes from the fault read.
- While the token is expired and the value poll has not renewed it yet (at most one poll interval), a fault read fails and the two fault entities are unavailable until the next read 10 minutes later.
- Tests guard the change by mutation: putting `_ensure_session` back fails the client tests.

## Related Decisions

- [ADR-Polling-019: Periodic ReadFaultMessages read for fault entities](ADR-Polling-019-fault-messages-read.md) — amended
- [ADR-Client-015: Login backoff survives restarts](ADR-Client-015-login-backoff-survives-restarts.md) — `AuthError` sets no block

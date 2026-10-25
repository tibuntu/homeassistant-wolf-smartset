# ADR-Client-015: Login backoff that survives restarts

## Status

Accepted

## Date

2026-10-25

## Context

This ADR supersedes [ADR-Client-014](ADR-Client-014-login-backoff.md). It kept the login block in a process-wide table only. On 2026-10-25 the owner's installation ran into a portal block: after many logins that day (restarts, re-setups, fixture recording), the hourly token renewal at 19:31 got a login page without form, and every later attempt as well. The coordinator backed off as designed. A Home Assistant restart during such a block, for example to load a new version, empties the table, and the setup logs in again at once. That is one more credential POST from the blocked IP and resets the doubling.

## Decision

1. The client keeps the process-wide table `_login_backoff` in `api/__init__.py`, keyed by the lower-cased username, holding the monotonic time until which logins are blocked and the number of consecutive failures.
2. Before every login, `_ensure_session` checks the table. While blocked it raises `LoginFailed` without any request.
3. Every failure of `_login` except `AuthError` records a block of `min(300 s · 2^failures, 3600 s)`. A successful login clears the entry. A wrong password sets no block. A bearer token the portal rejects right after a fresh login counts as a failed login as well.
4. **New:** `WolfClient` takes an optional `on_login_backoff` callback, called whenever the account's entry is set or cleared. The API module stays free of Home Assistant; it offers `get_login_backoff` (block end as wall-clock epoch seconds, failures) and `restore_login_backoff`.
5. **New:** The integration persists the table in `.storage/wolf_smartset.login_backoff`, one entry per account keyed by the SHA-256 of the lower-cased username, never the username itself. Setup and the config flow restore the entry before creating a client, so a block, and the failure count for the next doubling, outlive a restart. A later block already in memory wins over the stored one.
6. The coordinator treats `LoginFailed` like `TooManyRequests` and `PortalUnavailable`: the poll interval doubles up to one hour and a repair issue appears after three steps. The config flow shows `portal_unavailable`.
7. ErrorCode 6 raises `Maintenance`, a subclass of `PortalUnavailable`, so it takes the same backoff path.
8. The diagnostics show `login_blocked_seconds`.

## Rationale

The rationale of ADR-Client-014 holds: the table must outlive client instances because Home Assistant creates new ones for setup retries and config flows. A restart is the same situation one level up. Storing wall-clock time is necessary because monotonic time starts anew with the process; a clock jump shifts the block by the jump, which is harmless at this scale. Hashing the username keeps an identifying value out of a file that has nothing else to do with credentials.

### Alternatives Considered

**Keep the block in memory only (ADR-Client-014)**

- Pro: no storage file.
- Con: every restart during a block logs in again; restarts are what users do when something looks broken.

**Store the block in the config entry's data**

- Pro: no extra file.
- Con: writing entry data during a poll triggers update listeners; the config flow has no entry yet.

## Consequences

### Positive

- A restart during a portal block sends no credentials until the block ends.

### Negative

- After a long outage the integration may wait up to one hour after a restart before it logs in.
- One more `.storage` file.

### Risks

- A block that was set for a local reason (DNS, proxy) also survives a restart. The error message names the remaining time, and it is at most one hour.

## Related Decisions

- [ADR-Client-014: Login backoff across client instances](ADR-Client-014-login-backoff.md) — superseded by this ADR
- [ADR-Client-001: Own thin API client](ADR-Client-001-own-thin-api-client.md)
- [ADR-Polling-003: Polling strategy](ADR-Polling-003-polling-strategy.md)

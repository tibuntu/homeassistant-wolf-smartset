# ADR-Client-014: Login backoff across client instances

## Status

Superseded by [ADR-Client-015](ADR-Client-015-login-backoff-survives-restarts.md)

## Date

2026-10-25

## Context

The review of 0.2.0.dev2 (`docs/reviews/2026-10-25-write-pipeline.md`, finding 3) traced what happens when a login fails with something other than `AuthError`, `PortalUnavailable` or `TooManyRequests`: a timeout at the token endpoint, a non-JSON answer or an `invalid_grant` error leave the client without a token, and every poll logs in again with a full credential POST. During setup, Home Assistant retries `async_setup_entry` up to every ten minutes, each time with a fresh `WolfClient`, so the coordinator's backoff never applies. Up to thirty logins per hour during a Wolf outage is exactly the pattern that triggered IP blocks in the past (discovery, section 3.3; HA #113492, #155531), and the block also hits the SmartSet app on the same IP.

ADR-Client-001 promised a typed `Maintenance` error; the client mapped ErrorCode 6 to the generic `ApiError`.

## Decision

1. The client keeps a process-wide table `_login_backoff` in `api/__init__.py`, keyed by the lower-cased username, holding the monotonic time until which logins are blocked and the number of consecutive failures.
2. Before every login, `_ensure_session` checks the table. While blocked it raises `LoginFailed` without any request.
3. Every failure of `_login` except `AuthError` records a block of `min(300 s · 2^failures, 3600 s)`. A successful login clears the entry. A wrong password sets no block, because its retries come from the user through the reauth dialog. A bearer token the portal rejects right after a fresh login (a second HTTP 401 within one request) counts as a failed login as well.
4. The coordinator treats `LoginFailed` like `TooManyRequests` and `PortalUnavailable`: the poll interval doubles up to one hour and a repair issue appears after three steps. The config flow shows `portal_unavailable`.
5. ErrorCode 6 raises `Maintenance`, a subclass of `PortalUnavailable`, so it takes the same backoff path.
6. The diagnostics show `login_blocked_seconds`.

## Rationale

The table lives in the module, not in the client instance, because the instances that matter most are the short-lived ones: Home Assistant creates a new client for every setup retry and the config flow creates one per attempt. A per-instance counter would brake none of them. Keying by username keeps two config entries for different accounts independent and makes a second entry for the same account share the brake.

Five minutes as the first step follows the ioBroker fork's experience (1 → 4 → 16 min) and stays short enough that a brief Wolf hiccup costs one poll interval, while the cap of one hour matches the coordinator's maximum backoff.

### Alternatives Considered

**Backoff in the coordinator only**

- Pro: no module-level state.
- Con: setup retries create a new client every time and keep logging in, up to six times per hour.

**Backoff in the client only**

- Pro: one place.
- Con: the coordinator would keep polling at the normal interval and fail instantly each time; no repair issue, no longer interval during an outage.

## Consequences

### Positive

- At most one credential POST per block period per account, whatever created the client.
- An outage is visible as a repair issue instead of a silent login storm.

### Negative

- After an outage ends, the integration waits for the current block to expire (up to one hour) before logging in again.
- The table is process state; tests must clear it (autouse fixture in `tests/conftest.py`).

### Risks

- A login that fails for a reason local to this installation (DNS, proxy) is braked the same way. The error message names the remaining block time.

## Related Decisions

- [ADR-Client-001: Own thin API client](ADR-Client-001-own-thin-api-client.md)
- [ADR-Polling-003: Polling strategy](ADR-Polling-003-polling-strategy.md)
- [ADR-Client-015: Login backoff that survives restarts](ADR-Client-015-login-backoff-survives-restarts.md) — supersedes this ADR

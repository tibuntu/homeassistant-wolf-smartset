# ADR-Polling-003: Polling strategy

## Status

Accepted

## Date

2026-10-25

## Context

The SmartSet cloud has no push interface for third parties. Values come from `GetParameterValues`, one request per `BundleId`. Relevant facts (discovery, sections 3 and 11):

- The only published limit is `MaxSystemBusSamplingRateSec = 60`. Below 60 s, ioBroker saw up to 75 % empty responses. Core `wolflink` polls every 60 s; ioBroker defaults to 120 s.
- Requesting many values, especially expert-level ones, led to empty answers and once to HTTP 400 and missing expert values even in the portal.
- Polling a `BundleId` that does not exist for the system made the portal show "access blocked, invalid configuration" until the IP changed.
- The gateway pushes values of active bundles; expert-level values may freeze when no expert session is open.
- Logins, not polls, are what Wolf limits most aggressively.
- The heat-pump description spans seven bundles; the user-level tabs share bundle 1000.

Entities that are disabled in the registry are never added to Home Assistant. `DataUpdateCoordinator` tracks a context per listening entity (`async_contexts()`), so the coordinator can see which entities are active without private access.

## Decision

We will use one `DataUpdateCoordinator` per SmartSet system. All coordinators of a config entry share one API client and one session.

- **Interval:** default 120 s, configurable in the options flow, minimum 60 s.
- **What is fetched:** each entity registers its `ParameterId` as coordinator context. Each cycle requests only the bundles that contain active parameters, and within a bundle only those `ValueId`s. Bundle IDs come exclusively from the current description.
- **Request shape:** full requests (`LastAccess: null`, `GuiIdChanged: true` on the first request per bundle after a description load, `false` afterwards). Delta polling with the `LastAccess` cursor stays out of the MVP; we measure whether it is worth it in Phase 2.
- **Online check:** one system-state request per cycle. When the system is offline, entities become unavailable and value requests are skipped.
- **Description reload:** at setup, after a read error that hints at changed IDs, and once per day. The current values embedded in the description seed the coordinator data, so entities have values right after setup.
- **Backoff:** on `ToManyRequests`, portal unavailable, HTTP 429 or a cycle where every value request comes back empty, the coordinator raises `UpdateFailed` and doubles its interval up to one hour. A successful cycle restores the configured interval. After three consecutive backoff steps we raise a repair issue.
- **Unreadable parameters:** when a bundle fails with a read error, we retry its parameters one by one, remember the ones that fail and skip them until the next description reload (heatwrite strategy).
- `PARALLEL_UPDATES = 0` for read-only platforms and `1` for platforms that write.

## Rationale

One coordinator per system matches the device model and core `wolflink`. A shared client keeps one login and one session per account, which is the main defence against IP blocks. 120 s follows ioBroker's experience and stays well above the server minimum. Fetching only active parameters keeps the request count and the gateway load low, and it removes the many-values problem for expert-level data that users have not enabled.

Full requests are proven by core `wolflink`; delta polling with the cursor has subtle merge semantics (empty answer means "unchanged", not "missing"), which we want to measure before relying on it.

### Alternatives Considered

**Fixed 60 s like core `wolflink`, all user-level parameters**

- Pro: proven; simple.
- Con: polls parameters nobody uses; no headroom when expert values are enabled.

**One coordinator per bundle**

- Pro: different intervals per bundle are possible.
- Con: more coordinators, more requests aligned at the same time, no clear benefit for our use cases.

**Delta polling with `LastAccess` from the start**

- Pro: smaller responses.
- Con: unclear semantics; core does not use it; harder to test.

## Consequences

### Positive

- Request count scales with enabled entities, not with the size of the description.
- Clear, bounded reaction to throttling.

### Negative

- A newly enabled entity shows a value only after the next cycle or a description reload.
- 120 s means up to two minutes of delay for state changes made outside HA.

### Risks

- Expert-level values may stay frozen without an expert session. Measured 2026-10-27 (`docs/phase2-measurements.md`): the expert bundle delivers values when it is activated (`GuiIdChanged: true`: setup, reload, daily description refresh) and then freezes, while bundle 1000 updates on every poll. Documented as a limitation in the README; periodic re-activation is a separate decision.

## Related Decisions

- [ADR-Client-001: Own thin API client](ADR-Client-001-own-thin-api-client.md)
- [ADR-Writes-004: Write confirmation and rejected writes](ADR-Writes-004-write-confirmation-and-rejected-writes.md)
- [ADR-Client-014: Login backoff across client instances](ADR-Client-014-login-backoff.md)

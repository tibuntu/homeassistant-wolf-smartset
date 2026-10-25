# ADR-Integration-000: Standalone integration instead of piggybacking on `wolflink`

## Status

Proposed

## Date

2026-10-25

## Context

The core integration `wolflink` (Wolf SmartSet Service) is read-only. Two existing custom components add writing by attaching to it: `heatwrite` reads `entry.runtime_data`, `coordinator._wolf_client`, `_gateway_id` and the name-mangled `WolfClient._WolfClient__request`, and it temporarily flips `expert_mode` on the client that `wolflink` owns. `wolflink-write` guesses attribute names on whatever it finds in `runtime_data` and `hass.data` (see `docs/discovery.md`, sections 6.3 and 6.4).

Our hard rules forbid touching private attributes or `runtime_data` of other integrations. `wolflink` was restructured in 2026.7 (hub model) and is being migrated to `httpx2` on `dev`, so its internals change several times per year.

The installation uses the owner's main SmartSet account (decision by the owner, 2026-10-25). The Wolf cloud blocks the client's public IP for minutes up to an hour after too many logins, and the block also hits the SmartSet app and portal on the same IP (discovery, sections 3.3 and 11). HA issue #155531 showed that several clients logging in at the same HA start are enough to trigger it.

## Decision

We will build a standalone integration with the domain `wolf_smartset`. It has its own config flow (username, password, system selection), its own reauth flow, its own API client and its own entities. It does not import, read or depend on `wolflink`.

We recommend that users disable the core `wolflink` config entry once `wolf_smartset` is set up. Our integration provides the user-level sensors as well, so nothing is lost. For this installation we will disable `wolflink` before the first start of `wolf_smartset` in Phase 2. We will record a snapshot of the `wolflink` sensor values beforehand to compare our readings against.

## Rationale

Piggybacking avoids a second login and a second credential copy, which is its only real advantage. It breaks rule 3, it cannot become a Core PR, and it fails silently or loudly every time `wolflink` changes its internals. A standalone integration owns its session, so we control login frequency, backoff and write behaviour end to end.

Running both integrations in parallel works technically, because the cloud accepts several sessions per account. It doubles the login rate on the same IP, though, and with the main account an IP block also locks the owner out of the app. Disabling `wolflink` removes that risk at no functional cost.

### Alternatives Considered

**Piggyback on `wolflink` (heatwrite model)**

- Pro: one login, one session, no duplicate credentials.
- Con: violates rule 3; depends on private attributes; mutates another integration's client; not acceptable for Core.

**Run `wolf_smartset` and `wolflink` side by side permanently**

- Pro: users keep their existing `wolflink` entity history untouched.
- Con: two logins at every HA start and on every token expiry from the same IP; double polling load; higher risk of an IP block that also hits the app.

**Contribute writing directly to core `wolflink`**

- Pro: no new integration for users.
- Con: requires a published library with the missing features first; review cycle of months; the owner needs the functionality now. Remains the long-term path (see ADR-Client-001).

## Consequences

### Positive

- No dependency on another integration's internals; rule 3 holds by construction.
- Full control over login frequency, session lifetime and backoff.
- A realistic path to a later Core PR.

### Negative

- Users enter credentials a second time.
- Entity IDs and history differ from `wolflink`; we do not migrate history.
- Users who keep both integrations double the cloud load. The README must say so.

### Risks

- A user keeps `wolflink` enabled and gets IP-blocked. Mitigation: README warning and a repair issue when a `wolflink` entry for the same account is loaded.

## Related Decisions

- [ADR-Client-001: Own thin API client](ADR-Client-001-own-thin-api-client.md)
- [ADR-Model-006: Device model](ADR-Model-006-device-per-wolf-device.md)

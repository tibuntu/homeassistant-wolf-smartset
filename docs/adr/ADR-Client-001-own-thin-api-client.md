# ADR-Client-001: Own thin API client instead of wolf-comm

## Status

Accepted

## Date

2026-10-25

## Context

`wolf-comm` 0.0.52 is the only Python client for the SmartSet cloud. It handles login, session keep-alive, system list, value reads and a `write_value` call. It falls short for us in ways that sit in its core (discovery, section 6.1):

- The parameter mapping drops `Group`, `NamePrefix`, `ControlType`, `MinValue`/`MaxValue`/`StepWidth`/`Decimals` and the embedded current value.
- It deduplicates by `value_id`, first occurrence wins, so the writable variant of a parameter and its `BundleId` get lost. All `ValueId 0` placeholders collapse into one pseudo-parameter.
- Descriptors with units it does not know (`K`, `min`, `m³/h`, …) are dropped on purpose.
- The raw description is only reachable through a private, name-mangled method.
- Every request, including `WriteParameterValues`, is retried after HTTP 401 or 500. A write that the server executed but answered with 500 gets sent twice.
- It ignores the cloud's error codes (`InvalidSession`, `SystemOffline`, `ToManyRequests`) and re-runs the full login on every token expiry.

Core `wolflink` pins `wolf-comm==0.0.52`. A custom integration requiring a different version fights that pin on every HA start. Upstream fixes would reach us only after a release and a Core bump. The repository has no issue tracker and sees sporadic maintenance.

The owner has no expert (Fachmann) password. The client therefore never calls `ExpertLogin`.

## Decision

We will write our own small API client as a subpackage `custom_components/wolf_smartset/api/`. It has no Home Assistant imports and receives its `httpx.AsyncClient` from the caller.

Scope of the client:

1. OIDC authorization code + PKCE login against `https://www.wolf-smartset.com/idsrv` with client `smartset.web`, ported from wolf-comm with an Apache-2.0 attribution notice. PKCE and the anti-forgery token extraction use the standard library (`hashlib`, `secrets`, `html.parser`), so the integration adds no requirements.
2. Token reuse for its full lifetime. Errors are split into wrong credentials (token endpoint returns `error`), portal unavailable (login page without token) and other failures.
3. Portal session: `CreateSession2`, `UpdateSession` at most every 60 s while polling, `CloseSystem` on unload.
4. Read endpoints: `GetSystemList`, system state (online flag and `AccessLevel`), `GetGuiDescriptionForGateway` returned raw, and `GetParameterValues` per bundle.
5. Write endpoint: `WriteParameterValues` with the portal's payload, string values, no automatic retry.
6. Typed exceptions for the cloud's `ErrorCode` enum, including `ToManyRequests`, `InvalidSession`, `SystemOffline` and `Maintenance`.

The client does not interpret the parameter description. That is the job of the parameter model (ADR-Model-002).

## Rationale

The gaps sit in wolf-comm's data model and request layer, which are exactly the parts we need. Working around them means calling private methods, which is the heatwrite pattern we reject. The pin conflict makes upstream changes useless to us in the short term. Our client stays small, roughly 400 to 600 lines, because the cloud API surface we need is small.

Keeping the client free of HA imports lets us test it against recorded responses without Home Assistant. It can later move into its own PyPI package, which the Quality Scale rule `dependency-transparency` requires for a Core PR.

### Alternatives Considered

**Use wolf-comm as-is**

- Pro: no auth code to maintain; shared fixes with core `wolflink`.
- Con: raw description only via private API; blind write retry; lossy model; version pinned by Core.

**Upstream PRs to wolf-comm**

- Pro: benefits core `wolflink` users too.
- Con: release and Core bump needed before we can use them; pin conflict until then; uncertain maintainer response. We may still offer the write-retry fix upstream independently.

**Fork wolf-comm**

- Pro: starts from working code.
- Con: inherits the class-per-unit model and dedup logic; the import name `wolf_comm` collides with the Core-pinned package.

## Consequences

### Positive

- No requirement conflicts with Core; no third-party dependencies beyond what HA ships.
- Full raw data available for the parameter model.
- Write behaviour is under our control: no duplicates, explicit errors.

### Negative

- We own the login flow. Wolf changes it several times per year (discovery, section 11).
- The HA migration from `httpx` to `httpx2` affects us directly.

### Risks

- A broken login after a Wolf change. Mitigation: login isolated in one module with fixture tests; a portal-unavailable state backs off instead of starting reauth.
- Silent token renewal (`prompt=none`) is only proven in JavaScript. We start with full login on expiry and measure login frequency in Phase 2.

## Related Decisions

- [ADR-Integration-000: Standalone integration](ADR-Integration-000-standalone-integration.md)
- [ADR-Model-002: Parameter model and entity mapping](ADR-Model-002-parameter-model-and-entity-mapping.md)
- [ADR-Polling-003: Polling strategy](ADR-Polling-003-polling-strategy.md)

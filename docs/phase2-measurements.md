# Phase 2 – Measurements against the real installation (read-only)

Installation: Wolf CHA heat pump, Link home (firmware 4.40), owner account. Writes stay disabled.

## 2026-10-25 – Fixture recording (`scripts/record_fixtures.py`)

| Check | Result |
|---|---|
| Login flow (OIDC + PKCE via `/idsrv/connect/authorize`) | works, 1 login for the whole run |
| Systems on the account | 1, own system |
| `AccessLevel` | 4 ("Fachmann schreiben"), present in `GetSystemList` and `GetSystemStateList` next to `GatewayState` |
| Parameter description | 288 parameters; identical model (platform, writability, bundle, device, label) to the wolf-comm heat-pump example used as test fixture |
| Devices | Heizgerät, Bedienmodul BM-2 0, Mischermodul MM1, ISM (BM-2 and MM1 are installed) |
| User-level values (bundle 1000, `GuiIdChanged: true`) | 57 requested, 57 returned, all `State 1` |
| Value without `Value` field | "Raumtemperatur" (36000000001), presumably no room sensor connected; entity shows unknown |
| Values missing in the description but returned by the poll | 3 (mixer pump, mixer motor, compressor frequency) |

Redaction finding: `GetSystemList` returns `GatewayUsername`, which equals the Link home serial number on the device label. The recording script now redacts it. Other free-text fields contain only Wolf's standard texts.

## Next measurements (HA test run)

- Logins per day and time between logins (diagnostics `login_count`, `last_login`); expectation: about one per token lifetime.
- Throttling: backoff steps and repair issues over 24 h at the default 120 s interval.
- Expert values: enable a few expert sensors (for example Sparfaktor, heating curve) and check whether their values change or freeze without an expert session.
- Parallel operation is not part of the test: core `wolflink` is disabled before the first start (ADR-Integration-000).

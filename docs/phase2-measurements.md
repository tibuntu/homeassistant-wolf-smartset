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

## 2026-10-25 – Review of the running v0.1.0 (recorder, read-only)

| Check | Result |
|---|---|
| "Verdichterfrequenz", "MKP Mischerkreispumpe", "Mischermotor MM" | not permanently `unknown`: `unknown` at setup (no value in the description), first values at the first poll 2 min later (`0.0`, `1`, `0`). Fixed by a poll right after setup (ADR-Model-008) |
| "Raumtemperatur" | `unknown`, no value from the portal (no room sensor) |
| Verbrauch, JAZ, TAZ, MAZ | `0.0`; no S0 meter connected. No visibility condition in the description, WP110 shows 1000 regardless |
| ValueId prefix vs. device | unanimous for 4, 19, 22, 27, 36; no evidence for 35 (DHW). See ADR-Model-009 |

## 2026-10-26 – Availability before and after 0.2.1 (recorder, read-only)

Source: the recorder database of the owner's Home Assistant, transitions of `sensor.*_warmwassertemperatur` to and from `unavailable`, read with a read-only SQLite query. The integration does not log logins, so the outages are the measurable trace of a failed hourly token renewal. Times in CET.

| Up since | Down at | Up for | Note |
|---|---|---|---|
| 25.10. 19:04 | 19:31 | 27 min | discovery 16: "login page without form" |
| 25.10. 21:50 | 22:07 | 17 min | restarts and re-setups during the review remediation |
| 25.10. 22:12 | 22:38 | 26 min | |
| 25.10. 22:42 | 22:52 | 10 min | |
| 26.10. 08:52 | 10:32 | 100 min | hourly retry succeeded, discovery 16 |
| 26.10. 12:13 | none until 27.10. 11:12 | 23 h | `.storage/wolf_smartset.login_backoff` emptied at 12:13 by the successful login; the 0.3.0 and 0.4.0 updates and two entity-enable reloads (2 s each) left no gap |

Result: before 0.2.1 the integration lost the portal 17 to 100 minutes after each login; since 12:13 it survived 23 hourly token renewals. That matches the hypothesis of discovery 16 (a still valid IdentityServer session answers `/connect/authorize` with the code instead of the form). Closed 27.10.: a full day without an outage.

## 2026-10-27 – Expert-level values without an expert session (recorder, read-only)

Setup: Sparfaktor, Sockeltemperatur and Vorlauftemperatur Heizkurve (bundle 6300, Bedienmodul BM-2) were enabled on 26.10. 18:50 CET. They are settings and cannot show a freeze (unchanged and frozen look the same), so "Außentemperatur (Einstellungen und Anzeigen)" from the same bundle was enabled at 22:31 CET and compared with the user-level "Außentemperatur" of the Heizgerät (bundle 1000). Recorder rows per hour, times UTC.

| Hour (UTC) | User copy (bundle 1000): changes, last value | Expert copy (bundle 6300): changes, last value |
|---|---|---|
| 26.10. 21 | 7, 10.8 | 5, 10.3 (enabled 21:31) |
| 26.10. 22 | 1, 11.0 | 2, 10.5 (0.4.0 update, entry reload 21:41) |
| 26.10. 23 to 27.10. 02 | 2 to 8 per hour, 11.2 to 11.8 | 0 |
| 27.10. 03 | 5, 11.7 | 1, 11.4 |
| 27.10. 04 to 10 | 2 to 7 per hour, 11.5 to 13.8 | 0 |

Result: the expert bundle delivers fresh values when it is activated (`GuiIdChanged: true` on the first read after setup, reload or the daily description refresh) and then freezes; the single refresh at 03 UTC is unexplained. Bundle 1000 updates on every poll. The settings (Sparfaktor 0.5, Sockeltemperatur 29.0, Vorlauftemperatur Heizkurve 40.0) look the same either way. This confirms wolflink-write and ioBroker #242 (discovery 3.4). The two copies differ by about 0.5 K (BM-2 value versus Heizgerät value), which is not an integration issue.

Consequences: expert entities show a daily snapshot, documented in the README. An applied expert write read back through a frozen bundle would be reported as `confirmed: false` (README: expert writes unproven). Decided 2026-10-27: the snapshot semantics stay. Periodic re-activation (`GuiIdChanged: true` on every expert poll) or `IsSubBundle: true` gets a one-day test only if expert writes are ever wanted.

## Next measurements (HA test run)

- Logins per day: not logged; only the diagnostics (`login_count`, `last_login`) have them. Availability from the recorder is the proxy (section above).
- Throttling: backoff steps and repair issues over 24 h at the default 120 s interval.
- Expert values: measured, see the section above. Still open: whether a write to an expert parameter is confirmed through the frozen bundle, and whether `GuiIdChanged: true` on every poll or `IsSubBundle: true` keeps the bundle fresh without throttling.
- Parallel operation is not part of the test: core `wolflink` is disabled before the first start (ADR-Integration-000).

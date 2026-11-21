# Backlog briefs

One brief per finding of the feature research of 2026-11-20 (integration 0.6.1, Home Assistant 2026.10.4). Each brief is written for an agent that picks it up without the research conversation. Work one brief per branch and pull request. Delete the brief in the pull request that completes it: code, ADR and changelog are the record from then on.

| # | Brief | Status | Size |
|---|---|---|---|
| 03 | [PV-surplus DHW blueprint](03-pv-surplus-dhw-blueprint.md) | ready | small |
| 04 | [Fixture-grade diagnostics](04-fixture-grade-diagnostics.md) | ready | medium |
| 06 | [Icon translations](06-icon-translations.md) | ready | JSON |
| 07 | [Registry cleanup on platform change](07-registry-cleanup-on-platform-change.md) | ready | small |
| 08 | [Fault-message endpoints](08-fault-message-endpoints.md) | needs owner go at step 3 | investigation |
| 09 | [Dashboard section strategy](09-dashboard-section-strategy.md) | needs owner decision | unknown |
| 10 | [Config entry functions return None](10-config-entry-functions-return-none.md) | waits for the next HA bump | small |
| 12 | [Polling health sensors](12-parked-polling-health-sensors.md) | parked | |
| 13 | [Two-speed polling](13-parked-two-speed-polling.md) | parked | |
| 14 | [water_heater entity](14-parked-water-heater-entity.md) | parked | |

An orchestrating agent starts from [`ORCHESTRATOR.md`](ORCHESTRATOR.md). Suggested order: 01, 02, 03, then 04. Parked briefs record why an idea was set aside and what would reopen it; implement one only when its "Revisit when" condition holds.

## Evidence labels

- **measured**: read-only query on the owner's recorder, 2026-11-06 to 2026-11-20, CHA heat pump with BM-2 and MM1, poll interval 120 s.
- **verified**: read in this repository's code or in a CI log.
- **reported**: from web research, not checked against the primary source. Check it before building on it.

## Rules for every brief

These rules come from the owner and are recorded here because no other file in the repository states them together.

1. **Real writes need the owner's explicit go in chat.** Everything else is developed and tested against fixtures and with dry run on. Every write path goes through `WriteManager` (dry run, no-op suppression, rate limit, one write at a time): each write lands in the controller's EEPROM.
2. **Identifiers stay out** of code, logs, fixtures, entity attributes and commits: credentials, system and gateway IDs, serial numbers, system names, IP and MAC addresses. Recorded responses are redacted; `scripts/check-fixtures.sh` guards the fixtures.
3. **Unknown API behaviour is documented and asked about.** Call only endpoints and BundleIds that the integration already uses or that the owner approved. A poll with an invalid BundleId has locked a portal account by IP (`docs/discovery.md`, section 3.3).
4. **`ExpertLogin` is never called.** Expert (Fachmann) parameters are read-only.
5. **Other integrations' private attributes and `runtime_data` are theirs.**
6. **Translation keys are a public interface** and change only by addition ([ADR-Model-016](../adr/ADR-Model-016-stable-translation-keys.md)). State values stay Wolf's display texts.
7. **Settled decisions stay settled** unless the owner reopens them: no `climate` entity, no editing of weekly time programs from Home Assistant, party and holiday mode only on demand, the controller's weekly program is the baseline and Home Assistant handles exceptions.
8. **Outward-facing actions are the owner's**: commenting on or reopening issues, releases, anything on the real heating system or the owner's Home Assistant.

Git conventions are in [`CLAUDE.md`](../../CLAUDE.md). The merge gate is `.github/workflows/tests.yaml` (ruff, mypy, bandit, pytest with 95 % branch coverage) plus the hassfest and HACS workflows. Decisions go into a new ADR under `docs/adr/` (existing ADRs are superseded, never edited); measurements go into `docs/phase2-measurements.md`.

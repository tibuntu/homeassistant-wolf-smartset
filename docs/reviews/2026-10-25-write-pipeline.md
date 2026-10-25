# Review 2026-10-25: write pipeline (0.2.0.dev2, commit b540cee)

Read-only review of the integration against ADR-Writes-012 (ADR-Writes-004 and -005 are superseded by it), the Home Assistant Quality Scale and the owner's hard rules. Everything ran offline against the recorded fixtures. CONFIRMED means reproduced or traced through the code; PLAUSIBLE means reasoned, not verified.

The reproductions of findings 1 to 3 live in `tests/test_review_findings.py` as strict `xfail` tests that assert the desired behaviour. Fixing a finding makes its test pass; remove the marker in the same change.

Status later the same day: findings 1 and 7 are fixed in commit c31b7b0 (ADR-Writes-013 supersedes ADR-Writes-012; written values are held for 30 s and until the value was polled, pending records become `confirmed: false` after a restart). The first real writes took place with the owner's approval (discovery, section 14). Findings 2 and 3 remain open; their tests stay `xfail`.

## Verdict

Writes on the owner's own system for manual, user-level changes are acceptable: validation against the Wolf description, no-op suppression, rate limit, lock and dry run (default on) are implemented correctly and covered by behaviour tests; no path reaches `ExpertLogin`, and no service or attribute bypasses `write.py`. A public HACS release is not yet responsible: documentation is missing, Bronze is formally unmet, and the write path has three Major gaps. Biggest risk: at write time the integration cannot tell an applied write from an unapplied one (response body ignored, no recorded real write response), and a poll inside the first 30 s after a write reverts the optimistic state, so a retrying automation writes the same value to the EEPROM twice.

## Gates

| Gate | Result |
|---|---|
| `uv sync --locked --group dev` | pass |
| `uv run ruff check .`, `uv run ruff format --check .` | pass |
| `uv run mypy custom_components/` | pass (15 files) |
| `uv run bandit -c pyproject.toml -r custom_components/` | pass (0 findings) |
| `uv run pytest` | pass, 71 tests, 89.54 % branch coverage (gate 85 %) |
| `scripts/check-fixtures.sh` | pass |
| hassfest, HACS validation | not runnable locally; manifest checked by hand |

## Findings

### Major

1. `write.py:146-162` with `coordinator.py:146-158`: write/poll race. A poll inside the 30 s window after a write, or one in flight during it, replaces `coordinator.data` with the gateway's old value; the optimistic state is lost, `_pending` stays, and `same_value` then compares against the stale value, so a re-triggered automation writes the same value again. CONFIRMED (reproduced through the HA stack). **Fixed in c31b7b0.**
2. `api/__init__.py:374` with `write.py:189-211`: the `WriteParameterValues` response body is never inspected; anything without `ErrorCode`/`ErrorType` is recorded `ok`. No real write response is recorded in `tests/fixtures/` (nothing was ever written), so the success criterion is unvalidated. CONFIRMED.
3. `api/__init__.py:276-277` with `coordinator.py:118-124`: login repetition without backoff. A login failing with `CannotConnect` or `ApiError` (token endpoint timeout, non-JSON, `invalid_grant`) leaves `_token` empty; every poll and every HA setup retry (up to every 600 s) posts the credentials again, up to 30 logins per hour during a Wolf outage. Backoff exists only for `PortalUnavailable`/`TooManyRequests`. CONFIRMED; the IP block itself PLAUSIBLE.
4. `README.md:5`: documentation "follows". Installation, configuration, removal, expert writes without `ExpertLogin` (unproven, discovery 4.9) and the IP-block warning are missing; Quality Scale `docs-*` rules unmet. CONFIRMED.

### Minor

5. `write.py:79`: `access_level is None` allows the write (fail-open) when the portal omits `AccessLevel`. CONFIRMED.
6. `write.py:110,173` with `config_flow.py:188`: the rate-limit window is in memory; an HA restart or saving the options (`OptionsFlowWithReload`) resets the hourly counter. CONFIRMED.
7. `write.py:111` with `__init__.py:53-54`: `_pending` is not persisted; a write shortly before an HA restart is never confirmed or corrected. CONFIRMED. **Fixed in c31b7b0** (such records become `confirmed: false`, `read_back: null`).
8. `number.py:37` and `write.py:94`: `step or 1.0` is a hard-coded fallback. All 71 number parameters of the real description carry `StepWidth`; the direction is fail-safe. CONFIRMED (no occurrence), risk PLAUSIBLE.
9. `model.py:206`: `BundleId or 1000`; a tab without `BundleId` would be polled with 1000, which ADR-Polling-003 forbids (ioBroker #459). PLAUSIBLE.
10. `config_flow.py:196-198`: options are not validated server-side (interval below 60 s, writes per hour outside 1 to 60). CONFIRMED.
11. `translations/de.json`: `config` and `issues` sections missing. CONFIRMED.
12. `config_flow.py:87-91,116,140`: uncovered branches (`unknown`, `no_systems`, `no_system_selected`); Bronze rule `config-flow-test-coverage` unmet. CONFIRMED.
13. `coordinator.py:164-176,180-195`: isolation after `ParameterReadError` (up to 57 single requests in a burst, no pause) and the daily description reload are untested; "reload after a read error that hints at changed IDs" from ADR-Polling-003 is not implemented. CONFIRMED.
14. `tests/test_write.py`: guards without a test that fails when the guard is removed: the 30 s threshold (`write.py:220`), dry runs and no-ops not counting towards the limit, expiry of the rolling hour, history limit 200, history restore after restart (`async_load`), undo under dry run must not set `undone`, expert parameter at AccessLevel 2 gives `access_denied`, numeric no-op tolerance ("50.0" vs "50"). CONFIRMED.
15. `pyproject.toml:3` and `.release-please-manifest.json` say 0.1.0, `manifest.json` says 0.2.0.dev2. CONFIRMED.
16. `__init__.py:80-82`: the `wolflink_active` repair issue fires for any loaded `wolflink` entry, not only for the same account as ADR-Integration-000 says. CONFIRMED.
17. `api/__init__.py:152-161`: no typed `Maintenance` (ErrorCode 6) exception as ADR-Client-001 promises; it becomes `ApiError` and `UpdateFailed` without backoff. CONFIRMED.
18. `model.py:111-112`: `KNOWN_SWITCHES` yields `Kind.SWITCH` regardless of `writable`; a read-only account gets a switch whose every call ends in `not_writable` (the guard holds). CONFIRMED.
19. No brand icon; the `brands` check of hacs/action probably fails. PLAUSIBLE.
20. `scripts/record_fixtures.py:105-118`: `values_*.json` only passes `redact_ids`, not `redact_description`; text values of a user bundle (none today) would land unredacted. PLAUSIBLE.

### Nit

21. `sensor.py:82-85`: `CT_HIDDEN` in `_numeric` is dead code (`model.py:252` skips hidden parameters).
22. `entity.py:15,72` and `entity.py:29-36`: placeholder handling duplicated between `raw_value` and `parse_number`.
23. `docs/adr/*`: all 13 ADRs carry the date 2026-10-25 although Phase 0 is dated 2026-10-14; ADR-Model-008 and -011 repeat whole sections.
24. `write.py:53,85`: `format_number(-0.0)` gives "-0"; `float(target)` in the undo path raises `ValueError` for a comma value instead of `ServiceValidationError`.
25. `__init__.py:57-59`: the writer listener keeps the coordinator polling (`GetSystemStateList`, `UpdateSession`) even with every entity disabled.

## Quality Scale

Formally below Bronze, materially close to Silver. Cheapest steps to Bronze: tests for the three config-flow branches (12), README sections for installation, configuration, removal and risks (4), brand icon (19). Silver then needs coverage of 95 % or more, which means tests for the error paths in `coordinator.py` and `api/__init__.py` (13).

## Decisions needed before implementation

1. **Finding 1.** Decided: ADR-Writes-013 holds the written value for 30 s and until the value was polled.
2. **Finding 2.** Real writes have happened (discovery, section 14: "Antwort des Portals ohne Fehler"), but the shape of the response body is still not recorded in `tests/fixtures/`. Record it on the next approved write and define the success criterion from it, or reintroduce read-back confirmation as in ADR-Writes-004?
3. **Finding 3.** Which error classes count as a failed login, how long the backoff is, and whether HA setup retries reuse the client.

## Suggested task grouping (files must not overlap for parallel work)

| Task | Findings | Files | Tier |
|---|---|---|---|
| A race and pending persistence | 1, 7 | done in c31b7b0 | – |
| B write response | 2 | api/__init__.py, write.py, test_api.py | standard, after A and decision 2 |
| C login backoff | 3, 17 | api/__init__.py, coordinator.py, test_api.py, test_init.py | standard, after B |
| D docs and release | 4, 11, 15, 19 | README.md, de.json, pyproject.toml | mechanical, parallel to A to C |
| E missing tests | 12, 13, 14 | test_config_flow.py, test_init.py, test_write.py | mechanical, after A |
| F small fixes | 5, 6, 8, 9, 10, 16, 18, 21, 22, 24, 25 | one line each | mechanical, one batch after C |

## Keep as it is

- One pipeline in `write.py` whose order matches ADR-012, with behaviour tests through the HA stack.
- `api/__init__.py`: no write retry (tested), state check in the OIDC flow, standard library only, no `ExpertLogin`, no requirements.
- Fixtures and git history free of IDs, e-mails, IPs, MACs and time programs; `GatewayUsername` recognised as the serial number and redacted; diagnostics redact nested data.
- Model: writability from `IsReadOnly`, `ControlType` and `AccessLevel`; limits from `MinValueCondition`; devices only from data evidence (ADR-Model-010).

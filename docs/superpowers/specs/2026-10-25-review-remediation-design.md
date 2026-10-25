# Review remediation 2026-10-25: design

Source: `docs/reviews/2026-10-25-write-pipeline.md`. Findings 1 and 7 are already fixed (commit c31b7b0, ADR-Writes-013). This design covers every remaining finding except 25, which is accepted as is. It is the input for the implementation plan that subagents execute.

## User decisions (already made)

1. Finding 2: record the real `WriteParameterValues` response first, decide on validation afterwards (STOP gate before the validation task).
2. Finding 3: login backoff in the client (module-level, per username, 5 min doubling to 60 min) and in the coordinator.
3. Scope: all open findings, 25 dropped.
4. README stays English; no German README.
5. Coverage gate goes to 95 %.
6. Tasks run on a branch in a worktree, T1 to T4 sequentially, T5 in parallel; spec under `docs/superpowers/specs/`.

## Global constraints

- Tests run offline against the recorded fixtures; no network, no credentials.
- Nothing writes to the real heating system; `DEFAULT_DRY_RUN` stays `True`. A real write is the owner's step after the merge.
- No credentials, gateway IDs, system IDs, serial numbers or personal data in code, logs, fixtures, history records or commits. `scripts/check-fixtures.sh` must pass.
- Every task leaves `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy custom_components/`, `uv run bandit -c pyproject.toml -r custom_components/` and `uv run pytest` green.
- Conventional Commits, small commits, no `Co-Authored-By` trailer (repo `CLAUDE.md`).
- Docs and ADRs in English, in the style of the existing ADRs (Status, Date, Context, Decision, Rationale, Alternatives, Consequences, Risks, Related Decisions).
- No new runtime dependencies. Deliberate shortcuts carry a `# ponytail:` comment naming the ceiling.
- Tests first: each behaviour change starts with a failing test.

## T1: record the write response (finding 2)

**Goal.** Every applied write keeps the portal's response body, redacted, in its history record so the owner can lift a real response from the diagnostics into a fixture.

**Change.** In `write.py`, `async_write` keeps the return value of `coordinator.client.write_value(...)` and stores `record["response"] = _redact_ids(response)` before `_record`. `_redact_ids` walks dicts and lists and replaces the value of every key in `{"SystemId", "GatewayId", "SessionId", "Id", "SystemShareId"}` with `"**REDACTED**"`; everything else is kept. No DEBUG log. History records already reach `.storage` and the diagnostics (last 50 without `system_id`), so nothing else changes.

**Tests** (`tests/test_write.py`, `tests/test_diagnostics.py`).
- `write_value` returns `{"Values": [{"ValueId": 35000900000, "Value": "55", "State": 1}], "SystemId": 1234, "GatewayId": 5678}`; the record's `response` keeps `Values` and has both IDs redacted; the stored history in `hass_storage` matches.
- The diagnostics text contains neither `1234` nor `5678` after such a write (extend `test_redaction` with one write under dry run off).

**Docs.** `tests/fixtures/README.md` names the convention `real/write_response_<n>.json` and the owner's steps: approved write, diagnostics download, copy `writes.history[-1].response`, run `scripts/check-fixtures.sh`. `docs/reviews/2026-10-25-write-pipeline.md` gets a status line for finding 2: recording in place, validation pending the fixture. The `xfail` test for finding 2 in `tests/test_review_findings.py` stays; its reason now names the fixture path.

**Out of scope.** Interpreting the body. That is a new decision and a new ADR once `write_response_0.json` exists.

## T2: login backoff (findings 3 and 17)

**Goal.** A failed login blocks further login attempts for the same account for a growing period, across client instances, so polls, HA setup retries and the config flow cannot repeat credential POSTs during a Wolf outage.

**Client (`api/__init__.py`).**
- Constants `LOGIN_BACKOFF_SECONDS = 300` and `LOGIN_BACKOFF_MAX_SECONDS = 3600`.
- Module-level `_login_backoff: dict[str, tuple[float, int]]` mapping the username to `(blocked_until, failures)` on the `time.monotonic()` clock. `# ponytail: process-wide dict, one HA instance per process`.
- New exceptions: `LoginFailed(WolfError)` ("login blocked after earlier failures") and `Maintenance(PortalUnavailable)`. `_raise_for_body` maps `ErrorCode 6` to `Maintenance`.
- `_ensure_session`, inside the lock, before `_login`: read the entry; if `now < blocked_until`, raise `LoginFailed(f"login blocked for {remaining} s after {failures} failed attempts")` without any request. Call `_login`; on `AuthError` re-raise unchanged and leave the entry untouched (wrong password goes to reauth, retries are user-driven); on any other `WolfError`, set the entry to `(now + min(LOGIN_BACKOFF_SECONDS * 2 ** failures, LOGIN_BACKOFF_MAX_SECONDS), failures + 1)` and re-raise the original exception; on success delete the entry.
- Property `login_blocked_seconds: int` (0 when not blocked) for the diagnostics.

**Coordinator (`coordinator.py`).** The backoff tuple in `_async_update_data` becomes `(TooManyRequests, PortalUnavailable, LoginFailed)`; `Maintenance` is covered as a subclass of `PortalUnavailable`. `_async_setup` keeps raising `UpdateFailed` for these, which gives `ConfigEntryNotReady`; the next setup retry hits the client-side block and makes no request.

**Config flow.** `LoginFailed` joins `TooManyRequests, PortalUnavailable` in `_validate` and maps to `portal_unavailable`.

**Diagnostics.** `client.login_blocked_seconds`.

**Tests.**
- `tests/conftest.py`: autouse fixture clearing `_login_backoff` before each test.
- `tests/test_api.py`: token endpoint answers 502: the first `get_systems` raises `CannotConnect` after exactly one credential POST, the next four raise `LoginFailed` with no further POST; advancing `time.monotonic` by 300 s allows one more attempt and the block grows to 600 s; a successful login clears the entry so a later token expiry logs in without a block; a wrong password (`AuthError`) sets no block; `ErrorCode 6` raises `Maintenance`; `login_blocked_seconds` reports the remaining time.
- `tests/test_init.py`: `get_description` raising `LoginFailed` leaves the entry in `SETUP_RETRY`, not reauth; `get_values` raising `LoginFailed` during a poll doubles the interval like `TooManyRequests`.
- `tests/test_config_flow.py`: `LoginFailed` shows `portal_unavailable`.
- `tests/test_review_findings.py`: remove the `xfail` marker from the finding-3 test; it now expects one credential POST.

**Docs.** `docs/adr/ADR-Client-014-login-backoff.md` (Accepted): context from the review (discovery 3.3, HA #113492, #155531), the decision above, alternatives "coordinator only" (setup retries unbraked) and "client only" (no repair issue), consequences (an outage shows `portal_unavailable` for up to an hour after it ends), related ADR-Client-001 and ADR-Polling-003. ADR-Client-001 and -003 get a line under Related Decisions pointing to 014.

## T3: missing tests and pyproject (findings 12, 13, 14, 15)

**Config flow (`tests/test_config_flow.py`).** `get_systems` raising `RuntimeError` shows `unknown`; an empty system list aborts with `no_systems`; the systems step with an empty selection shows `no_system_selected` and the form again.

**Coordinator (`tests/test_init.py`).**
- Two user-level values in one bundle; `get_values` raises `ParameterReadError` for the pair and for one of the single IDs: the other value arrives, a WARNING names the unreadable ID, it lands in `coordinator.unreadable`, and the next poll requests only the readable one.
- Daily reload: after `DESCRIPTION_MAX_AGE` plus one poll, `get_description` is called again; an unchanged description schedules no reload; a description with one parameter removed schedules a config entry reload (`async_schedule_reload` patched or the entry state observed).

**Write guards (`tests/test_write.py`).** Each test fails when its guard is removed:
- a poll 10 s after the write keeps `55` and leaves the record pending; a poll 40 s after decides (hold threshold `CONFIRM_AFTER_SECONDS`);
- dry runs and no-ops do not count towards `max_writes_per_hour`;
- a real write older than one hour no longer counts (freezer plus patched `time.monotonic`, or after T4 the history timestamps);
- the history keeps at most 200 records;
- `async_load` restores the history after a new `WriteManager` is created, and the undo button is available again;
- undo under dry run records `dry_run` and does not set `undone`;
- an expert parameter (Sparfaktor, `36000600001`, enabled in the registry first) at `AccessLevel` 2 gives `access_denied`;
- a current value of `"50.0"` and a target of `50` is a no-op.

**pyproject.** `version` aligned with `manifest.json` (`0.2.0.dev2`, release-please overwrites both at release); `--cov-fail-under=95`. Acceptance: `uv run pytest` passes at 95 % or more; if the coordinator and API error paths still leave a gap, add the missing API tests (429 on each login step, token response without `access_token`, `UpdateSession` after 60 s, second 401 and second `InvalidSession`, `close` with and without session) in the same task.

## T4: batch of small fixes (findings 5, 6, 8, 9, 16, 18, 20 to 24; 10 and 23 are void, see below)

One task, one commit per finding, each with its test.

- **5** `write.py` `validate`: `access_level is None` raises `access_denied` (fail-closed). Test: `SystemState(True, None)`.
- **6** `write.py`: delete `_writes`; the rate limit counts history records with `result` in `(RESULT_OK, RESULT_NOT_APPLIED)` whose `time` lies within the last hour (`dt_util.parse_datetime`, compare with `dt_util.utcnow()`). Test: after a restart (new `WriteManager`, `async_load`) earlier writes still count; `test_rate_limit` unchanged.
- **8** `model.py` `Parameter.kind`: `NUMBER` additionally requires `self.step` not `None` and greater than 0; `number.py` uses `parameter.step` without fallback and raises `ValueError` in `__init__` when it is missing; `write.py` `validate` uses `parameter.step` directly. Test: the DHW setpoint descriptor without `StepWidth` becomes `Kind.SENSOR`.
- **9** `model.py` `parse_description`: a tab without `BundleId` is skipped with one `logging.getLogger(__name__).warning` naming the tab; no `1000` fallback. Test: a tab stripped of `BundleId` contributes no parameter.
- **10** void: `NumberSelector.__call__` in Home Assistant already refuses values outside its `min` and `max` with `probatio.Invalid`, which the flow turns into `InvalidData`; the review's trace missed it. Only regression tests remain (options outside the limits raise `InvalidData`, floats are stored as integers), placed in T3.
- **16** `__init__.py` `_check_wolflink(hass, username)`: the issue is raised only when a loaded `wolflink` entry has the same `username` (case-insensitive). Test: a loaded `wolflink` entry with another username raises no issue; same username raises it.
- **18** `model.py` `Parameter.kind`: `KNOWN_SWITCHES` yields `Kind.SWITCH` only when `self.writable`; otherwise the list rules apply (`Kind.ENUM`). Test: `IsReadOnly: true` on `22004200000` gives an enum sensor.
- **20** `scripts/record_fixtures.py`: a pure function `secret_value_ids(description) -> set[int]` (ControlType in `SECRET_CONTROL_TYPES` or name matching `SECRET_PARAMETER`) and `redact_values(values, secret_ids)` blanking `Value` to `**REDACTED**`; `record` applies it to `values_<n>.json`. Test in `tests/test_record_fixtures.py` for both functions against the heat-pump fixture.
- **21** `sensor.py`: drop `CT_HIDDEN` from `_numeric` and from the import.
- **22** `entity.py`: `parse_number` keeps only the float conversion; the placeholder check lives in `raw_value`. Test: `parse_number("--")` is no longer part of the contract; `raw_value` tests cover placeholders.
- **23** `docs/adr/*.md`: `## Date` set from `git log --diff-filter=A --format=%ad --date=short -- <file>` per ADR.
- **24** `write.py`: `format_number` maps `-0.0` to `"0"`; `validate` turns a `ValueError` from `float(target)` into `ServiceValidationError` with translation key `invalid_number` (`en.json`, `de.json`). Tests: `format_number(-0.0) == "0"`; undo with a stored `old` of `"abc"` raises `invalid_number`.

## T5: documentation and brand (findings 4, 11, 19)

**README.md** (English) gains, in this order after the intro: Installation (HACS custom repository `tibuntu/homeassistant-wolf-smartset`, category Integration, restart, add the integration), Configuration (account, system selection, one entry per account), Options (poll interval 60 to 3600 s, dry run, writes per hour), Writing (existing section plus: switch the dry run off under Configure; expert parameters are written without `ExpertLogin` and it is unproven whether the controller applies them, the history shows `confirmed: false` when not; Wolf blocks the public IP after too many logins and the block also hits the SmartSet app; disable the core Wolf SmartSet Service integration for the same account), Removal (delete the entry; `.storage/wolf_smartset.<entry_id>.history` is left behind and can be deleted by hand), Known limitations (time programs, dates and times unmapped; entity names are Wolf's German labels; unofficial API, no support by Wolf), Troubleshooting (repair issues `throttled` and `wolflink_active`, reauth, diagnostics download). Keep the existing "Entities disabled by default" and "Writing" content.

**de.json** gains `config` (steps, errors, abort) and `issues`, translated from `en.json`; keys identical.

**Brand.** Check the installed Home Assistant (`.venv/lib/python3.14/site-packages/homeassistant`) for a loader of `custom_components/<domain>/brand/` assets. If it exists, add a neutral `icon.png` (no Wolf logo) and `icon@2x.png` in the documented size, and note in the README that the entry in `home-assistant/brands` is a follow-up. If it does not exist, add only the README note. The finding closes either way; the result is recorded in `docs/reviews/2026-10-25-write-pipeline.md`.

## Order and delegation

| Task | Tier | Files | Order |
|---|---|---|---|
| T1 record write response | standard | write.py, test_write.py, test_diagnostics.py, fixtures README, review doc, test_review_findings.py | first |
| T2 login backoff | standard | api/__init__.py, coordinator.py, config_flow.py, diagnostics.py, conftest.py, test_api.py, test_init.py, test_config_flow.py, test_review_findings.py, ADR-014, ADR-001, ADR-003 | after T1 |
| T3 tests and pyproject | mechanical | test_config_flow.py, test_init.py, test_write.py, test_api.py, pyproject.toml | after T2 |
| T4 batch fixes | standard | write.py, model.py, number.py, config_flow.py, __init__.py, sensor.py, entity.py, scripts/record_fixtures.py, docs/adr/*, translations, tests | after T3 |
| T5 docs and brand | mechanical | README.md, de.json, brand/, review doc (brand line only) | parallel from the start |

Branch `review-2026-10-25` in a git worktree; one pull request at the end so hassfest and HACS validation run in CI. Each task: implementer with failing tests first, then spec review and quality review; one final whole-branch review. After the merge the owner performs one approved real write and files the response as `tests/fixtures/real/write_response_0.json`; the validation of the body is a new decision.

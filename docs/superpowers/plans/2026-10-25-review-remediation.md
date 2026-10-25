# Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the open findings of the 2026-10-25 review: record real write responses, stop login storms with a client-side backoff, fill the test gaps, fix the small defects and write the user documentation.

**Architecture:** Five tasks on one branch. T1 extends the write pipeline's history record, T2 adds a process-wide login backoff to the HA-free API client plus coordinator handling, T3 and T4 are tests and one-line fixes on the existing modules, T5 is documentation and brand assets. T1 to T4 run in sequence because they share `write.py` and the test files; T5 runs in parallel because its files are disjoint.

**Tech Stack:** Python 3.14, Home Assistant 2026.10 custom integration, httpx (MockTransport in tests), pytest-homeassistant-custom-component, probatio, uv, ruff, mypy, bandit, Pillow (dev only, for the icon).

**Spec:** `docs/superpowers/specs/2026-10-25-review-remediation-design.md` (findings: `docs/reviews/2026-10-25-write-pipeline.md`)

## Global Constraints

- Work on branch `review-2026-10-25` in a git worktree created from `main`; never on `main` directly.
- Tests run offline; no network, no credentials. `DEFAULT_DRY_RUN` stays `True`. Nothing in this plan writes to the real heating system.
- No credentials, gateway IDs, system IDs, serial numbers or personal data in code, logs, fixtures, history records or commits. `scripts/check-fixtures.sh` must pass.
- After every task these commands pass from the repo root: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy custom_components/`, `uv run bandit -c pyproject.toml -r custom_components/`, `uv run pytest`.
- Conventional Commits, one commit per step that says "Commit", no `Co-Authored-By` trailer (repo `CLAUDE.md`).
- Docs and ADRs in English, ADRs in the structure of `docs/adr/ADR-Writes-013-write-pipeline-with-explicit-confirmation.md`.
- No new runtime dependencies (`manifest.json` `requirements` stays `[]`).
- Tests first: write the failing test, run it, then implement. Existing tests keep passing.
- Line length 100, ruff isort settings as in `pyproject.toml` (`force-sort-within-sections`, `combine-as-imports`).
- The redaction marker is the string `**REDACTED**` everywhere (same as `scripts/record_fixtures.py`).
- Login backoff values: first block 300 s, doubling per consecutive failure, cap 3600 s, keyed by the lower-cased username, cleared by a successful login.

**User decisions (already made):**
- Finding 2: record the real write response first; interpreting it is a later decision behind a STOP gate (one approved real write by the owner).
- Finding 3: backoff in the client (module-level, per username) and in the coordinator.
- Scope: all open findings; finding 25 is accepted as is; finding 23 is void (git shows every ADR was created on its stated date); finding 10 is void (`NumberSelector` already validates min and max server-side), only regression tests remain.
- README stays English only.
- Coverage gate rises to 95 %.
- T1 to T4 sequential, T5 parallel; branch in a worktree; one pull request at the end.

## Review Focus

1. A write answered with HTTP 200 and an HTML body (portal login page after session loss) must end as `write_failed` with history `error`, never as `ok`. Test added to Task 3 (`test_write_value_non_json_body`).
2. Two client instances for `User@Example.com` and `user@example.com` must share one login block. Test added to Task 2 (`test_backoff_key_ignores_case`).
3. History records written by 0.2.0.dev1 have no `time` field; the history-based rate limit must skip them instead of crashing. Test added to Task 4 (`test_rate_limit_ignores_records_without_time`).
4. The options form delivers floats (`120.0`, `5.0`); they must be accepted and stored as integers. Test added to Task 3 (`test_options_accept_floats`).
5. A write response that is a JSON list instead of an object must be stored redacted without error. Test added to Task 1 (`test_write_response_is_kept_redacted`, parametrized).

---

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `custom_components/wolf_smartset/api/__init__.py` | HA-free portal client; login, session, read, write; new: login backoff, `LoginFailed`, `Maintenance` | T2 |
| `custom_components/wolf_smartset/coordinator.py` | polling, backoff on throttling; new: `LoginFailed` in the backoff tuple | T2 |
| `custom_components/wolf_smartset/config_flow.py` | config, reauth, options; new: `LoginFailed` mapping, option validation | T2, T4 |
| `custom_components/wolf_smartset/write.py` | write pipeline and history; new: `redact_ids`, response in the record, history-based rate limit, fail-closed access level, `invalid_number` | T1, T4 |
| `custom_components/wolf_smartset/model.py` | parameter model; new: `NUMBER` needs a step, switch needs writability, tabs without `BundleId` skipped | T4 |
| `custom_components/wolf_smartset/number.py`, `sensor.py`, `entity.py`, `__init__.py`, `diagnostics.py` | one-line changes | T2, T4 |
| `custom_components/wolf_smartset/translations/en.json`, `de.json` | new key `invalid_number`; German `config` and `issues` | T4, T5 |
| `custom_components/wolf_smartset/brand/` | `icon.png`, `icon@2x.png` | T5 |
| `scripts/record_fixtures.py`, `scripts/brand_icon.py` | fixture recording with value redaction; icon generator | T4, T5 |
| `tests/*` | behaviour tests per task | all |
| `docs/adr/ADR-Client-014-login-backoff.md`, `README.md`, `tests/fixtures/README.md`, `docs/reviews/2026-10-25-write-pipeline.md` | documentation | T1, T2, T4, T5 |

---

### Task 1: Record the write response in the history

**Goal:** Every applied write keeps the portal's response body, with identifiers redacted, in its history record so the owner can lift a real response from the diagnostics into a fixture.

**Files:**
- Modify: `custom_components/wolf_smartset/write.py` (constants after line 48, `async_write` lines 193-209)
- Modify: `tests/test_write.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_review_findings.py` (replace the file)
- Modify: `tests/fixtures/README.md`
- Modify: `docs/reviews/2026-10-25-write-pipeline.md` (status line of finding 2)

**Acceptance Criteria:**
- [ ] After a real write the history record has a key `response` holding the body returned by `write_value`, with the values of `SystemId`, `GatewayId`, `SessionId`, `Id` and `SystemShareId` replaced by `**REDACTED**` at any nesting depth, lists included.
- [ ] The stored history in `.storage` and the diagnostics carry the same redacted response.
- [ ] Dry runs, no-ops, rate-limited and failed writes have no `response` key.
- [ ] `tests/test_review_findings.py` contains only the finding-2 and finding-3 tests (finding 1 is covered by `test_early_poll_keeps_the_written_value` in `tests/test_write.py`).

**Verify:** `uv run pytest tests/test_write.py tests/test_diagnostics.py tests/test_review_findings.py -q` → all pass, 1 xfailed (finding 2), 1 xfailed (finding 3)

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_write.py`:

```python
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            {
                "Values": [{"ValueId": DHW_SETPOINT, "Value": "55", "State": 1}],
                "SystemId": 1234,
                "GatewayId": 5678,
            },
            {
                "Values": [{"ValueId": DHW_SETPOINT, "Value": "55", "State": 1}],
                "SystemId": "**REDACTED**",
                "GatewayId": "**REDACTED**",
            },
        ),
        (
            [{"ValueId": DHW_SETPOINT, "State": 1, "SessionId": 42}],
            [{"ValueId": DHW_SETPOINT, "State": 1, "SessionId": "**REDACTED**"}],
        ),
    ],
)
async def test_write_response_is_kept_redacted(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
    response: Any,
    expected: Any,
) -> None:
    """The portal's answer lands in the record and in .storage without identifiers."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    mock_client.write_value.return_value = response
    await _set_setpoint(hass, 55)

    assert _history(mock_config_entry)[-1]["response"] == expected
    await hass.async_block_till_done()
    stored = hass_storage[f"{DOMAIN}.{mock_config_entry.entry_id}.history"]["data"]["history"]
    assert stored[-1]["response"] == expected


async def test_only_applied_writes_carry_a_response(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Dry runs and no-ops never talked to the portal, so they have no response."""
    await _setup(hass, mock_config_entry)  # dry run
    await _set_setpoint(hass, 55)
    assert "response" not in _history(mock_config_entry)[-1]
    await _set_setpoint(hass, 50)  # no-op
    assert "response" not in _history(mock_config_entry)[-1]
```

Append to `tests/test_diagnostics.py` (add `from homeassistant.helpers import entity_registry as er` and `from custom_components.wolf_smartset.const import CONF_DRY_RUN, DOMAIN` to the imports):

```python
async def test_write_response_in_diagnostics_is_redacted(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The last 50 history records, response included, show no identifiers."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_DRY_RUN: False})
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    mock_client.write_value.return_value = {
        "Values": [{"ValueId": 35000900000, "State": 1}],
        "SystemId": 1234,
        "GatewayId": 5678,
    }
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, "1234_35000900000")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 55}, blocking=True
    )

    result = await get_diagnostics_for_config_entry(hass, hass_client, mock_config_entry)
    record = result["writes"]["history"][-1]
    assert "system_id" not in record
    assert record["response"] == {
        "Values": [{"ValueId": 35000900000, "State": 1}],
        "SystemId": "**REDACTED**",
        "GatewayId": "**REDACTED**",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_write.py tests/test_diagnostics.py -q --no-cov -k "response"`
Expected: FAIL with `KeyError: 'response'` (the parametrized test) and PASS for `test_only_applied_writes_carry_a_response` (nothing is stored yet, so the absence holds; keep it as a regression guard).

- [ ] **Step 3: Implement `redact_ids` and store the response**

In `custom_components/wolf_smartset/write.py`, after `RESULT_NOT_APPLIED = "not_applied"` (line 48) add:

```python
# Keys of portal responses that identify the installation or the session.
_ID_KEYS = frozenset({"SystemId", "GatewayId", "SessionId", "Id", "SystemShareId"})
REDACTED = "**REDACTED**"


def redact_ids(data: Any) -> Any:
    """Replace identifiers in a portal response so the record can be shared."""
    if isinstance(data, list):
        return [redact_ids(item) for item in data]
    if isinstance(data, dict):
        return {k: REDACTED if k in _ID_KEYS else redact_ids(v) for k, v in data.items()}
    return data
```

In `async_write`, change the API call so the return value is kept:

```python
            try:
                response = await coordinator.client.write_value(
                    coordinator.system,
                    parameter.bundle_id,
                    parameter.value_id,
                    target,
                    parameter.name,
                )
```

and directly after `self._writes.append(now)` add:

```python
            record["response"] = redact_ids(response)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_write.py tests/test_diagnostics.py -q --no-cov`
Expected: all PASS

- [ ] **Step 5: Replace `tests/test_review_findings.py`**

The two finding-1 tests duplicate `test_early_poll_keeps_the_written_value`. Replace the whole file with:

```python
"""Reproductions of the open findings of the 2026-10-25 review.

See docs/reviews/2026-10-25-write-pipeline.md.

Each test asserts the desired behaviour and is marked xfail(strict=True) until the finding
is fixed. A fixed finding makes its test pass, which fails the strict xfail: remove the marker
in the same change.
"""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wolf_smartset.api import (
    AUTH_URL,
    REDIRECT_URI,
    CannotConnect,
    WolfClient,
)
from custom_components.wolf_smartset.const import CONF_DRY_RUN, DOMAIN

DHW_SETPOINT = 35000900000  # "Warmwassersolltemperatur eingestellt", 25-65 °C, step 1, value 50


def _entity_id(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"1234_{DHW_SETPOINT}")
    assert entity_id
    return entity_id


async def _setup_writable(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={CONF_DRY_RUN: False})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _set_setpoint(hass: HomeAssistant, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value", {"entity_id": _entity_id(hass), "value": value}, blocking=True
    )


@pytest.mark.xfail(
    strict=True,
    reason="Finding 2: the WriteParameterValues response body is not interpreted yet; "
    "the real response is recorded as tests/fixtures/real/write_response_0.json first, "
    "this body is a placeholder",
)
async def test_write_response_reporting_an_error_is_not_ok(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A response that reports State 5 (Error) for the written value must not count as applied."""
    await _setup_writable(hass, mock_config_entry)
    mock_client.write_value.return_value = {"Values": [{"ValueId": DHW_SETPOINT, "State": 5}]}
    await _set_setpoint(hass, 55)
    assert mock_config_entry.runtime_data.writer.history[-1]["result"] != "ok"


LOGIN_PAGE = '<form><input type="hidden" name="__RequestVerificationToken" value="tok"/></form>'


@pytest.mark.xfail(
    strict=True,
    reason="Finding 3: a failed token exchange leaves the token empty, and every later call "
    "posts the credentials again without any backoff",
)
async def test_failed_token_exchange_does_not_relogin_on_every_call() -> None:
    """Five calls against a broken token endpoint must not post the credentials five times."""
    logins = 0
    state = ""

    def portal(request: httpx.Request) -> httpx.Response:
        nonlocal logins, state
        url = str(request.url)
        if url.startswith(f"{AUTH_URL}/connect/authorize"):
            state = request.url.params["state"]
            return httpx.Response(
                302, headers={"Location": f"{AUTH_URL}/Account/Login?ReturnUrl=x"}
            )
        if url.startswith(f"{AUTH_URL}/Account/Login") and request.method == "GET":
            return httpx.Response(200, text=LOGIN_PAGE)
        if url.startswith(f"{AUTH_URL}/Account/Login"):
            logins += 1
            return httpx.Response(302, headers={"Location": f"{REDIRECT_URI}?code=c&state={state}"})
        if url.startswith(REDIRECT_URI):
            return httpx.Response(200, text="ok")
        if url == f"{AUTH_URL}/connect/token":
            return httpx.Response(502, text="<html>bad gateway</html>")
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        client = WolfClient(http, "user", "pw")
        for _ in range(5):
            with pytest.raises(CannotConnect):
                await client.get_systems()
    assert logins < 5
```

Run: `uv run pytest tests/test_review_findings.py -q --no-cov`
Expected: `2 xfailed`

- [ ] **Step 6: Document the fixture convention and the status**

Append to `tests/fixtures/README.md`:

```markdown
- `real/write_response_<n>.json`: the body the portal returned for one `WriteParameterValues` call, taken from the `response` field of the write history. Record it after an approved real write: Settings › Devices & services › Wolf SmartSet › Download diagnostics, copy `writes.history[-1].response` into the file, run `scripts/check-fixtures.sh`. Identifiers are already redacted by the integration (`write.redact_ids`). No such file exists yet; interpreting the body is a separate decision (`docs/reviews/2026-10-25-write-pipeline.md`, decision 2).
```

In `docs/reviews/2026-10-25-write-pipeline.md`, finding 2, append to the line: ` **Recording in place (T1 of the remediation plan): every applied write stores the redacted response in its history record; the fixture and the validation are the owner's next step.**`

- [ ] **Step 7: Run the gates and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy custom_components/ && uv run pytest -q`
Expected: all pass, coverage ≥ 85 %, `2 xfailed`

```bash
git add custom_components/wolf_smartset/write.py tests/test_write.py tests/test_diagnostics.py tests/test_review_findings.py tests/fixtures/README.md docs/reviews/2026-10-25-write-pipeline.md
git commit -m "feat: keep the redacted write response in the history record"
```

```json:metadata
{"files": ["custom_components/wolf_smartset/write.py", "tests/test_write.py", "tests/test_diagnostics.py", "tests/test_review_findings.py", "tests/fixtures/README.md", "docs/reviews/2026-10-25-write-pipeline.md"], "verifyCommand": "uv run pytest tests/test_write.py tests/test_diagnostics.py tests/test_review_findings.py -q", "acceptanceCriteria": ["applied writes store record['response'] with SystemId, GatewayId, SessionId, Id, SystemShareId redacted at any depth, lists included", ".storage and diagnostics carry the same redacted response", "dry runs, no-ops, rate-limited and failed writes have no response key", "test_review_findings.py holds only the finding-2 and finding-3 xfail tests"], "modelTier": "standard"}
```

---

### Task 2: Login backoff in the client and the coordinator

**Goal:** A failed login blocks further login attempts for the same account for a growing period across client instances, so polls, HA setup retries and the config flow cannot repeat credential POSTs during a Wolf outage; ErrorCode 6 becomes a typed `Maintenance` error.

**Files:**
- Modify: `custom_components/wolf_smartset/api/__init__.py` (constants after line 35, exceptions after line 59, `_raise_for_body` line 152, `_ensure_session` lines 273-277)
- Modify: `custom_components/wolf_smartset/coordinator.py` (imports lines 17-29, except tuple line 122)
- Modify: `custom_components/wolf_smartset/config_flow.py` (imports lines 29-37, `_validate` line 85)
- Modify: `custom_components/wolf_smartset/diagnostics.py` (client block lines 25-28)
- Modify: `tests/conftest.py`
- Modify: `tests/test_api.py` (`FakePortal`, new tests)
- Modify: `tests/test_init.py`, `tests/test_config_flow.py`, `tests/test_diagnostics.py`, `tests/test_review_findings.py`
- Create: `docs/adr/ADR-Client-014-login-backoff.md`
- Modify: `docs/adr/ADR-Client-001-own-thin-api-client.md`, `docs/adr/ADR-Polling-003-polling-strategy.md` (Related Decisions)

**Acceptance Criteria:**
- [ ] With a broken token endpoint, five consecutive `get_systems` calls post the credentials exactly once; calls two to five raise `LoginFailed` without any HTTP request.
- [ ] The block starts at 300 s, doubles per consecutive failure, is capped at 3600 s, is keyed by the lower-cased username, survives new `WolfClient` instances, and is cleared by a successful login.
- [ ] `AuthError` (wrong password) sets no block.
- [ ] `ErrorCode 6` raises `Maintenance`, a subclass of `PortalUnavailable`.
- [ ] The coordinator treats `LoginFailed` like throttling (interval doubles, repair issue after three steps); setup with `LoginFailed` ends in `SETUP_RETRY`, not reauth; the config flow shows `portal_unavailable`.
- [ ] Diagnostics report `client.login_blocked_seconds`.
- [ ] `docs/adr/ADR-Client-014-login-backoff.md` exists with status Accepted; ADR-001 and ADR-003 link to it.

**Verify:** `uv run pytest tests/test_api.py tests/test_init.py tests/test_config_flow.py tests/test_diagnostics.py tests/test_review_findings.py -q` → all pass, 1 xfailed (finding 2 only)

**Steps:**

- [ ] **Step 1: Extend `FakePortal` and write the failing client tests**

In `tests/test_api.py`, change `FakePortal.__init__` to add two attributes and the token branch to honour them:

```python
    def __init__(self) -> None:
        self.password = "secret"
        self.logins = 0
        self.calls: list[str] = []
        self.api: dict[str, Callable[[httpx.Request], httpx.Response]] = {}
        self.login_page = LOGIN_PAGE
        self.state = ""
        self.token_status = 200
        self.token_body: dict[str, Any] | None = None
```

```python
        if url == f"{AUTH_URL}/connect/token":
            if self.token_status != 200:
                return httpx.Response(self.token_status, text="<html>error</html>")
            form = parse_qs(request.content.decode())
            assert form["code_verifier"] and form["grant_type"] == ["authorization_code"]
            body = self.token_body or {"access_token": f"t{self.logins}", "expires_in": 3600}
            return httpx.Response(200, json=body)
```

Add `from typing import Any` and `import time` to the imports, and extend the `custom_components.wolf_smartset.api` import with `LOGIN_BACKOFF_MAX_SECONDS, LOGIN_BACKOFF_SECONDS, LoginFailed, Maintenance, _login_backoff`.

Append the tests:

```python
async def test_failed_login_blocks_further_attempts(client: WolfClient, portal: FakePortal) -> None:
    """One credential POST, then LoginFailed without any request until the block ends."""
    portal.token_status = 502
    with pytest.raises(CannotConnect):
        await client.get_systems()
    for _ in range(4):
        with pytest.raises(LoginFailed):
            await client.get_systems()
    assert portal.logins == 1
    assert portal.calls == []
    assert 0 < client.login_blocked_seconds <= LOGIN_BACKOFF_SECONDS
    assert _login_backoff["user"][1] == 1


async def test_backoff_doubles_and_resets(client: WolfClient, portal: FakePortal) -> None:
    """Each consecutive failure doubles the block; a successful login clears it."""
    portal.token_status = 502
    with pytest.raises(CannotConnect):
        await client.get_systems()
    _login_backoff["user"] = (time.monotonic() - 1, 1)  # the first block has ended
    with pytest.raises(CannotConnect):
        await client.get_systems()
    assert portal.logins == 2
    assert _login_backoff["user"][1] == 2
    assert client.login_blocked_seconds > LOGIN_BACKOFF_SECONDS

    _login_backoff["user"] = (time.monotonic() - 1, 2)
    portal.token_status = 200
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    assert await client.get_systems() == []
    assert "user" not in _login_backoff
    assert client.login_blocked_seconds == 0


async def test_backoff_is_capped(client: WolfClient, portal: FakePortal) -> None:
    """After many failures the block stays at the cap."""
    portal.token_status = 502
    _login_backoff["user"] = (0.0, 10)
    with pytest.raises(CannotConnect):
        await client.get_systems()
    assert (
        LOGIN_BACKOFF_MAX_SECONDS - 2 <= client.login_blocked_seconds <= LOGIN_BACKOFF_MAX_SECONDS
    )


async def test_backoff_key_ignores_case(portal: FakePortal) -> None:
    """Clients for 'User' and 'user' share one block."""
    portal.token_status = 502
    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        with pytest.raises(CannotConnect):
            await WolfClient(http, "User", portal.password).get_systems()
        with pytest.raises(LoginFailed):
            await WolfClient(http, "user", portal.password).get_systems()
    assert portal.logins == 1


async def test_wrong_password_sets_no_block(portal: FakePortal) -> None:
    """Invalid credentials go to reauth; retries are the user's."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        client = WolfClient(http, "user", "wrong")
        for _ in range(2):
            with pytest.raises(AuthError):
                await client.get_systems()
    assert "user" not in _login_backoff


async def test_token_response_without_token(client: WolfClient, portal: FakePortal) -> None:
    """A JSON error from the token endpoint is an ApiError and counts as a failed login."""
    portal.token_body = {"error": "invalid_grant"}
    with pytest.raises(ApiError):
        await client.get_systems()
    assert _login_backoff["user"][1] == 1
```

Extend the `test_error_mapping` parametrization with `({"ErrorCode": 6, "Message": "x"}, 200, Maintenance),` and add this test:

```python
def test_maintenance_is_portal_unavailable() -> None:
    """The coordinator's backoff tuple catches Maintenance through its base class."""
    assert issubclass(Maintenance, PortalUnavailable)
```

- [ ] **Step 2: Add the autouse fixture that clears the backoff**

In `tests/conftest.py` add `from custom_components.wolf_smartset import api` to the imports and:

```python
@pytest.fixture(autouse=True)
def clear_login_backoff() -> Generator[None]:
    """The login backoff is process-wide; every test starts without one."""
    api._login_backoff.clear()
    yield
    api._login_backoff.clear()
```

Also add `client.login_blocked_seconds = 0` to the `mock_client` fixture after `client.last_login = None`.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_api.py -q --no-cov`
Expected: ImportError for `LoginFailed` (collection fails)

- [ ] **Step 4: Implement the backoff in the client**

In `custom_components/wolf_smartset/api/__init__.py`, after `TOKEN_EXPIRY_MARGIN_SECONDS = 60` add:

```python
# A failed login blocks the next attempt for this long, doubling per failure (ADR-Client-014).
LOGIN_BACKOFF_SECONDS = 300
LOGIN_BACKOFF_MAX_SECONDS = 3600

# Lower-cased username -> (monotonic time until which logins are blocked, consecutive failures).
# ponytail: process-wide dict, one HA instance per process; it must outlive client
# instances so HA's setup retries and the config flow cannot log in again.
_login_backoff: dict[str, tuple[float, int]] = {}
```

After `class PortalUnavailable(WolfError)` add:

```python
class Maintenance(PortalUnavailable):
    """ErrorCode 6, the portal is in maintenance."""


class LoginFailed(WolfError):
    """Login blocked after earlier failures; no request was made."""
```

In `_raise_for_body`, add `case 6: raise Maintenance(message)` before `case 10`.

Replace the login branch of `_ensure_session` and add the helper and property:

```python
    async def _ensure_session(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._token is None or now >= self._token_expires:
                await self._login_with_backoff(now)
            if self._session_id is None:
```

```python
async def _login_with_backoff(self, now: float) -> None:
    """Log in unless an earlier failure still blocks this account."""
    key = self._username.lower()
    blocked_until, failures = _login_backoff.get(key, (0.0, 0))
    if now < blocked_until:
        raise LoginFailed(
            f"login blocked for {int(blocked_until - now)} s after {failures} failed attempts"
        )
    try:
        await self._login()
    except AuthError:
        raise
    except WolfError:
        delay = min(LOGIN_BACKOFF_SECONDS * 2**failures, LOGIN_BACKOFF_MAX_SECONDS)
        _login_backoff[key] = (now + delay, failures + 1)
        raise
    _login_backoff.pop(key, None)


@property
def login_blocked_seconds(self) -> int:
    """Seconds until the next login attempt is allowed, 0 when not blocked."""
    blocked_until, _ = _login_backoff.get(self._username.lower(), (0.0, 0))
    return max(0, int(blocked_until - time.monotonic()))
```

- [ ] **Step 5: Run the client tests to verify they pass**

Run: `uv run pytest tests/test_api.py -q --no-cov`
Expected: all PASS

- [ ] **Step 6: Write the failing integration tests**

Append to `tests/test_init.py` (extend the api import with `LoginFailed`):

```python
async def test_blocked_login_retries_setup(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A blocked login is temporary: setup retry, no reauth flow."""
    mock_client.get_description.side_effect = LoginFailed("blocked")
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress()


async def test_blocked_login_backs_off(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """LoginFailed during a poll doubles the interval like throttling."""
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinators[1234]
    mock_client.get_system_state.side_effect = LoginFailed("blocked")
    freezer.tick(coordinator.update_interval)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.update_interval == timedelta(seconds=240)
```

In `tests/test_config_flow.py`, extend the `test_errors_recover` parametrization with `(LoginFailed("x"), "portal_unavailable")` (import `LoginFailed`).

In `tests/test_diagnostics.py` `test_redaction`, add `assert result["client"]["login_blocked_seconds"] == 0`.

In `tests/test_review_findings.py`, delete the `@pytest.mark.xfail(...)` decorator of `test_failed_token_exchange_does_not_relogin_on_every_call` and change its last line to `assert logins == 1`.

Run: `uv run pytest tests/test_init.py tests/test_config_flow.py tests/test_diagnostics.py tests/test_review_findings.py -q --no-cov`
Expected: FAIL for the backoff test (interval stays 120), the config-flow case (`cannot_connect`), the diagnostics key, and the review test (`logins == 5`)

- [ ] **Step 7: Wire the coordinator, config flow and diagnostics**

`coordinator.py`: add `LoginFailed` to the `.api` import and change line 122 to `except (TooManyRequests, PortalUnavailable, LoginFailed) as err:`.

`config_flow.py`: add `LoginFailed` to the `.api` import and change the except clause to `except TooManyRequests, PortalUnavailable, LoginFailed:`.

`diagnostics.py`: in the `"client"` block add `"login_blocked_seconds": runtime.client.login_blocked_seconds,`.

Run: `uv run pytest tests/test_init.py tests/test_config_flow.py tests/test_diagnostics.py tests/test_review_findings.py -q --no-cov`
Expected: all PASS, 1 xfailed

- [ ] **Step 8: Write ADR-Client-014**

Create `docs/adr/ADR-Client-014-login-backoff.md`:

```markdown
# ADR-Client-014: Login backoff across client instances

## Status

Accepted

## Date

2026-10-25

## Context

The review of 0.2.0.dev2 (`docs/reviews/2026-10-25-write-pipeline.md`, finding 3) traced what happens when a login fails with something other than `AuthError`, `PortalUnavailable` or `TooManyRequests`: a timeout at the token endpoint, a non-JSON answer or an `invalid_grant` error leave the client without a token, and every poll logs in again with a full credential POST. During setup, Home Assistant retries `async_setup_entry` up to every ten minutes, each time with a fresh `WolfClient`, so the coordinator's backoff never applies. Up to thirty logins per hour during a Wolf outage is exactly the pattern that triggered IP blocks in the past (discovery, section 3.3; HA #113492, #155531), and the block also hits the SmartSet app on the same IP.

ADR-Client-001 promised a typed `Maintenance` error; the client mapped ErrorCode 6 to the generic `ApiError`.

## Decision

1. The client keeps a process-wide table `_login_backoff` in `api/__init__.py`, keyed by the lower-cased username, holding the monotonic time until which logins are blocked and the number of consecutive failures.
2. Before every login, `_ensure_session` checks the table. While blocked it raises `LoginFailed` without any request.
3. Every failure of `_login` except `AuthError` records a block of `min(300 s · 2^failures, 3600 s)`. A successful login clears the entry. A wrong password sets no block, because its retries come from the user through the reauth dialog.
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
```

Append to the Related Decisions list of `ADR-Client-001-own-thin-api-client.md` and `ADR-Polling-003-polling-strategy.md`:

```markdown
- [ADR-Client-014: Login backoff across client instances](ADR-Client-014-login-backoff.md)
```

- [ ] **Step 9: Run the gates and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy custom_components/ && uv run bandit -c pyproject.toml -r custom_components/ && uv run pytest -q`
Expected: all pass, `1 xfailed`

```bash
git add custom_components/wolf_smartset/api/__init__.py custom_components/wolf_smartset/coordinator.py custom_components/wolf_smartset/config_flow.py custom_components/wolf_smartset/diagnostics.py tests/conftest.py tests/test_api.py tests/test_init.py tests/test_config_flow.py tests/test_diagnostics.py tests/test_review_findings.py docs/adr/ADR-Client-014-login-backoff.md docs/adr/ADR-Client-001-own-thin-api-client.md docs/adr/ADR-Polling-003-polling-strategy.md
git commit -m "feat: block repeated logins after a failure, typed Maintenance error"
```

```json:metadata
{"files": ["custom_components/wolf_smartset/api/__init__.py", "custom_components/wolf_smartset/coordinator.py", "custom_components/wolf_smartset/config_flow.py", "custom_components/wolf_smartset/diagnostics.py", "tests/conftest.py", "tests/test_api.py", "tests/test_init.py", "tests/test_config_flow.py", "tests/test_diagnostics.py", "tests/test_review_findings.py", "docs/adr/ADR-Client-014-login-backoff.md", "docs/adr/ADR-Client-001-own-thin-api-client.md", "docs/adr/ADR-Polling-003-polling-strategy.md"], "verifyCommand": "uv run pytest tests/test_api.py tests/test_init.py tests/test_config_flow.py tests/test_diagnostics.py tests/test_review_findings.py -q", "acceptanceCriteria": ["five calls against a broken token endpoint post the credentials once; calls two to five raise LoginFailed without a request", "block 300 s doubling per failure, cap 3600 s, keyed by lower-cased username, survives new client instances, cleared by a successful login", "AuthError sets no block", "ErrorCode 6 raises Maintenance(PortalUnavailable)", "coordinator doubles the interval on LoginFailed; setup ends in SETUP_RETRY; config flow shows portal_unavailable", "diagnostics report client.login_blocked_seconds", "ADR-Client-014 exists, ADR-001 and ADR-003 link to it"], "modelTier": "standard"}
```

---

### Task 3: Missing tests and pyproject

**Goal:** Every guard of the write pipeline, the config-flow branches and the coordinator's error paths have a test that fails when the guard is removed; coverage reaches 95 % and the gate enforces it.

**Files:**
- Modify: `tests/test_config_flow.py`
- Modify: `tests/test_init.py`
- Modify: `tests/test_write.py`
- Modify: `tests/test_api.py`
- Modify: `pyproject.toml` (lines 3 and 54)

**Acceptance Criteria:**
- [ ] `tests/test_config_flow.py` covers `unknown`, `no_systems` and `no_system_selected`, pins that options outside the selector limits raise `InvalidData` and that floats are stored as integers; `config_flow.py` reaches 100 % coverage.
- [ ] `tests/test_init.py` covers the isolation of an unreadable value and the daily description reload with unchanged and changed descriptions.
- [ ] `tests/test_write.py` covers: the 30 s threshold, dry runs and no-ops not counting towards the limit, the rolling hour, the history limit of 200, history restore after reload, undo under dry run, expert parameter at access level 2, numeric no-op tolerance, `same_value` edge cases.
- [ ] `tests/test_api.py` covers 429 on every login step, `UpdateSession` after 60 s, repeated 401, `InvalidSession` on reads and writes, `close()` with and without a session, a non-JSON 200 write response, `SystemShareId` in the state request.
- [ ] `uv run pytest` reports total coverage ≥ 95 % with `--cov-fail-under=95` in `pyproject.toml`, and `version = "0.2.0.dev2"`.

**Verify:** `uv run pytest -q` → passes, `Required test coverage of 95% reached`

**Steps:**

- [ ] **Step 1: Config flow tests**

Append to `tests/test_config_flow.py`:

```python
async def test_unexpected_error(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Anything that is not a WolfError shows 'unknown' and is logged."""
    mock_client.get_systems.side_effect = RuntimeError("boom")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_no_systems(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """An account without systems cannot be added."""
    mock_client.get_systems.return_value = []
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_systems"


async def test_no_system_selected(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """An empty selection shows the systems step again with an error."""
    mock_client.get_systems.return_value = [SYSTEM, System(99, 98, "Cabin", 7)]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SYSTEMS: []})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "systems"
    assert result["errors"] == {"base": "no_system_selected"}


@pytest.mark.parametrize(
    "user_input",
    [
        {CONF_SCAN_INTERVAL: 10, CONF_DRY_RUN: True, CONF_MAX_WRITES_PER_HOUR: 5},
        {CONF_SCAN_INTERVAL: 120, CONF_DRY_RUN: True, CONF_MAX_WRITES_PER_HOUR: 0},
        {CONF_SCAN_INTERVAL: 120, CONF_DRY_RUN: True, CONF_MAX_WRITES_PER_HOUR: 61},
    ],
)
async def test_options_are_validated(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    user_input: dict[str, Any],
) -> None:
    """NumberSelector refuses values outside min and max server-side (review finding 10)."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    with pytest.raises(data_entry_flow.InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], user_input)


async def test_options_accept_floats(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The number selector delivers floats; they are stored as integers; the form serializes."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    fields = probatio.to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)
    assert len(fields) == 3
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 120.0, CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 5.0},
    )
    assert mock_config_entry.options == {
        CONF_SCAN_INTERVAL: 120,
        CONF_DRY_RUN: False,
        CONF_MAX_WRITES_PER_HOUR: 5,
    }
```

Add to the imports of `tests/test_config_flow.py`: `from typing import Any`, `from homeassistant import data_entry_flow`, `from homeassistant.helpers import config_validation as cv`, `import probatio`.

Run: `uv run pytest tests/test_config_flow.py -q --no-cov --cov=custom_components.wolf_smartset.config_flow --cov-report=term-missing` (drop `--no-cov` to see the report)
Expected: PASS (the option tests pass without a code change; they pin behaviour), `config_flow.py` 100 %

- [ ] **Step 2: Coordinator tests**

Append to `tests/test_init.py` (add `import copy`, `from typing import Any`, `from unittest.mock import patch`, `from custom_components.wolf_smartset.api import ParameterReadError`, `from custom_components.wolf_smartset.const import DESCRIPTION_MAX_AGE` to the imports, keeping the existing ones):

```python
async def test_unreadable_value_is_isolated(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bundle read error is retried per value; the bad value is skipped from then on."""
    await _setup(hass, mock_config_entry)
    bad = 35000900000  # DHW setpoint

    def read(system: Any, bundle: int, ids: list[int], first: bool = False) -> list[Value]:
        if bad in ids:
            raise ParameterReadError("internal msg: ReadParameterValues error")
        return [Value(i, "1", 1) for i in ids]

    mock_client.get_values.side_effect = read
    freezer.tick(timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    coordinator = mock_config_entry.runtime_data.coordinators[1234]
    assert coordinator.unreadable == {bad}
    assert f"Value {bad} of Home cannot be read" in caplog.text
    assert hass.states.get(_entity_id(hass, "switch", 22004200000)).state == "on"

    mock_client.get_values.reset_mock()
    freezer.tick(timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_values.call_args_list
    assert all(bad not in call.args[2] for call in mock_client.get_values.call_args_list)


async def test_description_is_reloaded_daily(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a day the description is fetched again; an unchanged one reloads nothing."""
    await _setup(hass, mock_config_entry)
    mock_client.get_description.reset_mock()
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        freezer.tick(DESCRIPTION_MAX_AGE + timedelta(seconds=130))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert mock_client.get_description.await_count == 1
    reload.assert_not_called()


async def test_changed_description_reloads_the_entry(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    description: dict[str, Any],
) -> None:
    """A description with other parameters schedules a config entry reload."""
    await _setup(hass, mock_config_entry)
    changed = copy.deepcopy(description)
    changed["MenuItems"][0]["TabViews"] = [
        tab for tab in changed["MenuItems"][0]["TabViews"] if tab["TabName"] != "Warmwasser"
    ]
    mock_client.get_description.return_value = changed
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        freezer.tick(DESCRIPTION_MAX_AGE + timedelta(seconds=130))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    reload.assert_called_once_with(mock_config_entry.entry_id)
```

Add `import pytest` to the imports of `tests/test_init.py`.

Run: `uv run pytest tests/test_init.py -q --no-cov`
Expected: PASS

- [ ] **Step 3: Write-guard tests**

Append to `tests/test_write.py` (add `from custom_components.wolf_smartset.write import CONFIRM_AFTER_SECONDS, same_value`, `from custom_components.wolf_smartset.model import parse_description` and `from custom_components.wolf_smartset.api import SystemState` where missing):

```python
async def test_confirmation_waits_for_the_threshold(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A poll one second before the threshold keeps the record pending; after it, decides."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 55)
    mock_client.get_values.side_effect = lambda system, bundle, ids, first=False: [
        Value(i, "55" if i == DHW_SETPOINT else "0", 1) for i in ids
    ]
    coordinator = mock_config_entry.runtime_data.coordinators[1234]

    freezer.tick(timedelta(seconds=CONFIRM_AFTER_SECONDS - 1))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _history(mock_config_entry)[-1]["confirmed"] is None

    freezer.tick(timedelta(seconds=2))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _history(mock_config_entry)[-1]["confirmed"] is True


async def test_dry_runs_and_no_ops_do_not_count(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Only real writes consume the hourly budget."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: True, CONF_MAX_WRITES_PER_HOUR: 1})
    await _set_setpoint(hass, 51)
    await _set_setpoint(hass, 52)  # two dry runs
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 1}
    )
    await _set_setpoint(hass, 50)
    await _set_setpoint(hass, 50)  # two no-ops
    await _set_setpoint(hass, 55)  # the one allowed real write
    assert mock_client.write_value.await_count == 1
    assert _history(mock_config_entry)[-1]["result"] == "ok"


async def test_rate_limit_window_rolls(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A write older than one hour no longer counts."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 1})
    await _set_setpoint(hass, 51)
    with pytest.raises(HomeAssistantError):
        await _set_setpoint(hass, 52)
    freezer.tick(timedelta(hours=1, seconds=1))
    await _set_setpoint(hass, 52)
    assert mock_client.write_value.await_count == 2


async def test_history_keeps_200_records(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Older records fall off the end."""
    await _setup(hass, mock_config_entry)  # dry run: every attempt is recorded
    for i in range(205):
        await _set_setpoint(hass, 51 + (i % 2))
    assert len(_history(mock_config_entry)) == 200
    assert _history(mock_config_entry)[-1]["new"] == "51"


async def test_history_survives_reload(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """After unload and setup the history is back and the undo button is available."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 55)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert _history(mock_config_entry)[-1]["new"] == "55"
    button = er.async_get(hass).async_get_entity_id("button", DOMAIN, "1234_undo")
    assert button
    assert hass.states.get(button).state != "unavailable"


async def test_undo_under_dry_run_changes_nothing(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Undo goes through the pipeline: with dry run on it only logs and keeps the record."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 55)
    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_DRY_RUN: True})
    button = er.async_get(hass).async_get_entity_id("button", DOMAIN, "1234_undo")
    assert button
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert mock_client.write_value.await_count == 1
    assert _history(mock_config_entry)[-1]["result"] == "dry_run"
    assert "undone" not in _history(mock_config_entry)[-2]


async def test_expert_parameter_needs_expert_access(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """AccessLevel 2 may write user parameters but not expert ones."""
    mock_client.get_system_state.return_value = SystemState(True, 2)
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_DRY_RUN: False})
    er.async_get(hass).async_get_or_create(
        "number", DOMAIN, "1234_36000600001", config_entry=mock_config_entry, disabled_by=None
    )  # enable Sparfaktor before setup
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": _entity_id(hass, "number", 36000600001), "value": 1.5},
            blocking=True,
        )
    assert err.value.translation_key == "access_denied"
    await _set_setpoint(hass, 55)
    assert mock_client.write_value.await_count == 1


async def test_no_op_compares_numerically(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """'50.0' and '50,0' are the same as 50."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    coordinator = mock_config_entry.runtime_data.coordinators[1234]
    for current in ("50.0", "50,0"):
        coordinator.data[DHW_SETPOINT] = current
        await _set_setpoint(hass, 50)
    mock_client.write_value.assert_not_called()


def test_same_value_edge_cases(description: dict[str, Any]) -> None:
    """Unknown or unparsable current values never count as equal."""
    parameters = parse_description(description).parameters
    setpoint, program = parameters[DHW_SETPOINT], parameters[PROGRAM]
    assert same_value(setpoint, None, "50") is False
    assert same_value(setpoint, "--", "50") is False
    assert same_value(setpoint, "50.0", "50") is True
    assert same_value(program, " 1 ", "1") is True
    assert same_value(program, None, "1") is False
```

Run: `uv run pytest tests/test_write.py -q --no-cov`
Expected: PASS

- [ ] **Step 4: API tests for the remaining error paths**

Append to `tests/test_api.py`:

```python
@pytest.mark.parametrize("step", ["connect/authorize", "Account/Login", "connect/token"])
async def test_429_during_login(portal: FakePortal, step: str) -> None:
    """HTTP 429 on any login step is throttling."""

    def throttled(request: httpx.Request) -> httpx.Response:
        if step in str(request.url):
            return httpx.Response(429)
        return portal(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(throttled)) as http:
        with pytest.raises(TooManyRequests):
            await WolfClient(http, "user", portal.password).get_systems()


async def test_session_is_refreshed_after_60_seconds(
    client: WolfClient, portal: FakePortal
) -> None:
    """UpdateSession runs before a request once the session is older than 60 s."""
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    portal.api["UpdateSession"] = lambda r: httpx.Response(200, json={"Maintenance": 0})
    await client.get_systems()
    client._session_refreshed -= 61
    await client.get_systems()
    assert portal.calls == ["CreateSession2", "GetSystemList", "UpdateSession", "GetSystemList"]


async def test_second_unauthorized_is_an_error(client: WolfClient, portal: FakePortal) -> None:
    """Only one relogin per request."""
    portal.api["GetSystemList"] = lambda r: httpx.Response(401)
    with pytest.raises(ApiError):
        await client.get_systems()
    assert portal.logins == 2


async def test_invalid_session_creates_a_new_session(
    client: WolfClient, portal: FakePortal
) -> None:
    """ErrorCode 1 once: new session and retry; twice: error."""
    answers = iter([{"ErrorCode": 1, "Message": "x"}, []])
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=next(answers))
    assert await client.get_systems() == []
    assert portal.calls.count("CreateSession2") == 2

    portal.api["GetSystemList"] = lambda r: httpx.Response(
        200, json={"ErrorCode": 1, "Message": "x"}
    )
    with pytest.raises(ApiError):
        await client.get_systems()


async def test_write_with_lost_session_is_not_retried(
    client: WolfClient, portal: FakePortal
) -> None:
    """A write answered with InvalidSession raises; the next call opens a new session."""
    portal.api["WriteParameterValues"] = lambda r: httpx.Response(
        200, json={"ErrorCode": 1, "Message": "x"}
    )
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    with pytest.raises(ApiError):
        await client.write_value(SYSTEM, 1000, 22004200000, "1", "1x Warmwasser")
    assert portal.calls.count("WriteParameterValues") == 1
    await client.get_systems()
    assert portal.calls.count("CreateSession2") == 2


async def test_write_value_non_json_body(client: WolfClient, portal: FakePortal) -> None:
    """HTTP 200 with an HTML body (login page) is an error, never a silent success."""
    portal.api["WriteParameterValues"] = lambda r: httpx.Response(200, text="<html>login</html>")
    with pytest.raises(ApiError):
        await client.write_value(SYSTEM, 1000, 22004200000, "1", "1x Warmwasser")


async def test_close_releases_the_session(client: WolfClient, portal: FakePortal) -> None:
    """CloseSystem is called once per session; errors are swallowed; no session, no call."""
    await client.close()
    assert "CloseSystem" not in portal.calls
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    portal.api["CloseSystem"] = lambda r: httpx.Response(500)
    await client.get_systems()
    await client.close()
    await client.close()
    assert portal.calls.count("CloseSystem") == 1


async def test_shared_system_state_request(client: WolfClient, portal: FakePortal) -> None:
    """Shared systems send their SystemShareId; values without State or Value are kept."""

    def state(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["SystemList"] == [{"SystemId": 1, "GatewayId": 2, "SystemShareId": 7}]
        assert payload["SessionId"] == 42
        return httpx.Response(200, json=[{"GatewayState": {"IsOnline": False}}])

    portal.api["GetSystemStateList"] = state
    result = await client.get_system_state(System(1, 2, "Home", 7))
    assert (result.online, result.access_level) == (False, None)

    portal.api["GetParameterValues"] = lambda r: httpx.Response(
        200, json={"Values": [{"ValueId": 7, "State": 0}]}
    )
    assert await client.get_values(SYSTEM, 1000, [7]) == [Value(7, None, 0)]
```

Add `Value` to the api import of `tests/test_api.py`.

Run: `uv run pytest tests/test_api.py -q --no-cov`
Expected: PASS

- [ ] **Step 5: pyproject**

In `pyproject.toml` change `version = "0.1.0"` to `version = "0.2.0.dev2"` and `"--cov-fail-under=85",` to `"--cov-fail-under=95",`.

Run: `uv run pytest -q`
Expected: `Required test coverage of 95% reached`. If the total is below 95 %, read the `Missing` column and add tests for the listed lines in the same files as above until it passes; do not lower the gate.

- [ ] **Step 6: Run the gates and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy custom_components/ && uv run pytest -q`
Expected: all pass

```bash
git add tests/test_config_flow.py tests/test_init.py tests/test_write.py tests/test_api.py pyproject.toml
git commit -m "test: cover the write guards, config flow branches and client error paths; gate 95 %"
```

```json:metadata
{"files": ["tests/test_config_flow.py", "tests/test_init.py", "tests/test_write.py", "tests/test_api.py", "pyproject.toml"], "verifyCommand": "uv run pytest -q", "acceptanceCriteria": ["config_flow.py at 100 % with tests for unknown, no_systems, no_system_selected, options outside the selector limits raising InvalidData, floats stored as integers", "isolation of an unreadable value and the daily description reload are tested", "write guards tested: 30 s threshold, dry runs and no-ops do not count, rolling hour, history limit 200, restore after reload, undo under dry run, expert parameter at level 2, numeric no-op tolerance, same_value edge cases", "api tests: 429 on every login step, UpdateSession after 60 s, repeated 401, InvalidSession on read and write, close with and without session, non-JSON 200 write response, SystemShareId", "pyproject version 0.2.0.dev2 and --cov-fail-under=95 with uv run pytest passing"], "modelTier": "mechanical"}
```

---

### Task 4: Batch of small fixes

**Goal:** Close findings 5, 6, 8, 9, 16, 18, 20, 21, 22 and 24 with one commit per finding, each with its test, and record the final status of every finding in the review document.

**Files:**
- Modify: `custom_components/wolf_smartset/write.py`
- Modify: `custom_components/wolf_smartset/model.py`
- Modify: `custom_components/wolf_smartset/number.py`
- Modify: `custom_components/wolf_smartset/__init__.py`
- Modify: `custom_components/wolf_smartset/sensor.py`
- Modify: `custom_components/wolf_smartset/entity.py`
- Modify: `custom_components/wolf_smartset/translations/en.json`, `de.json`
- Modify: `scripts/record_fixtures.py`
- Create: `tests/test_record_fixtures.py`
- Modify: `tests/test_write.py`, `tests/test_model.py`, `tests/test_init.py`, `tests/test_sensor.py`
- Modify: `docs/reviews/2026-10-25-write-pipeline.md`

**Acceptance Criteria:**
- [ ] 5: an unknown `AccessLevel` (`None`) refuses every write with `access_denied`.
- [ ] 6: the hourly limit counts history records with result `ok` or `not_applied` from the last hour; `WriteManager._writes` no longer exists; the count survives unload and setup; records without `time` are ignored.
- [ ] 8: a numeric parameter without `StepWidth` is a sensor; `number.py` and `write.py` have no `or 1.0` fallback.
- [ ] 9: a tab without `BundleId` is skipped with a warning; `model.py` has no `1000` fallback.
- [ ] 16: the `wolflink_active` issue appears only for a loaded `wolflink` entry with the same username.
- [ ] 18: `22004200000` with `IsReadOnly: true` is an enum sensor, not a switch.
- [ ] 20: `scripts/record_fixtures.py` exposes `secret_value_ids` and `redact_values`, applies them to `values_<n>.json`, and both are unit-tested.
- [ ] 21, 22: `CT_HIDDEN` gone from `sensor.py`; `parse_number` only converts.
- [ ] 24: `format_number(-0.0) == "0"`; an unparsable number raises `ServiceValidationError` with key `invalid_number` in both languages.
- [ ] The review document marks every finding fixed, void or accepted.

**Verify:** `uv run pytest -q` → passes at ≥ 95 %

**Steps:**

- [ ] **Step 1 (finding 5): fail-closed access level**

Test, in `tests/test_write.py`, replace `test_access_level_is_respected` with a parametrized version:

```python
@pytest.mark.parametrize("level", [1, None])
async def test_access_level_is_respected(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    level: int | None,
) -> None:
    """A read-only account, or one whose level is unknown, cannot write."""
    mock_client.get_system_state.return_value = SystemState(True, level)
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    with pytest.raises(ServiceValidationError) as err:
        await _set_setpoint(hass, 55)
    assert err.value.translation_key == "access_denied"
    mock_client.write_value.assert_not_called()
```

Run: `uv run pytest tests/test_write.py -q --no-cov -k access_level` → FAIL for `None`.

Implementation, `write.py` `validate`: change `if access_level is not None and access_level < required:` to `if access_level is None or access_level < required:`.

Run again → PASS. Commit: `git commit -am "fix: refuse writes while the access level is unknown"`.

- [ ] **Step 2 (finding 6): rate limit from the history**

Tests, append to `tests/test_write.py`:

```python
async def test_rate_limit_survives_reload(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The hourly budget is counted from the persisted history."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 1})
    await _set_setpoint(hass, 55)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await _set_setpoint(hass, 56)
    assert err.value.translation_key == "rate_limited"


async def test_rate_limit_ignores_records_without_time(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    """Records written by 0.2.0.dev1 carry no time; they neither count nor crash."""
    hass_storage[f"{DOMAIN}.{mock_config_entry.entry_id}.history"] = {
        "version": 1,
        "key": f"{DOMAIN}.{mock_config_entry.entry_id}.history",
        "data": {"history": [{"result": "ok", "old": "50", "new": "51"}]},
    }
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 1})
    await _set_setpoint(hass, 55)
    assert mock_client.write_value.await_count == 1
```

Run → FAIL (the first test writes a second time).

Implementation in `write.py`: add `from datetime import timedelta` to the imports; delete `self._writes: list[float] = []` from `__init__`; add the method

```python
    def _writes_last_hour(self) -> int:
        """Real writes (applied or not) recorded during the last hour."""
        cutoff = dt_util.utcnow() - timedelta(hours=1)
        return sum(
            1
            for record in self.history
            if record.get("result") in (RESULT_OK, RESULT_NOT_APPLIED)
            and (written := dt_util.parse_datetime(record.get("time") or "")) is not None
            and written >= cutoff
        )
```

and in `async_write` replace

```python
            now = time.monotonic()
            self._writes = [t for t in self._writes if now - t < 3600]
            if len(self._writes) >= self.max_writes_per_hour:
```

with

```python
            now = time.monotonic()
            if self._writes_last_hour() >= self.max_writes_per_hour:
```

and delete the line `self._writes.append(now)`.

Run `uv run pytest tests/test_write.py -q --no-cov` → PASS (including `test_rate_limit_window_rolls`, which now relies on `dt_util.utcnow` advanced by the freezer). Commit: `git commit -am "fix: count the hourly write budget from the persisted history"`.

- [ ] **Step 3 (finding 8): numbers need a step**

Test, append to `tests/test_model.py`:

```python
def _descriptors(description: dict[str, Any], value_id: int) -> list[dict[str, Any]]:
    """Every descriptor of a ValueId anywhere in the description."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("ValueId") == value_id:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(description)
    return found


def test_number_needs_a_step(description: dict[str, Any]) -> None:
    """Without StepWidth a numeric input cannot be validated, so it stays a sensor."""
    for descriptor in _descriptors(description, 35000900000):
        descriptor.pop("StepWidth", None)
    assert parse_description(description).parameters[35000900000].kind is Kind.SENSOR
```

Run → FAIL (`Kind.NUMBER`).

Implementation: in `model.py` `Parameter.kind` change `limits_ok` to

```python
            limits_ok = (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum < self.maximum
                and self.step is not None
                and self.step > 0
            )
```

In `number.py` `__init__`:

```python
        if parameter.minimum is None or parameter.maximum is None or parameter.step is None:
            raise ValueError(f"Parameter {parameter.parameter_id} has no limits")
        self._attr_native_min_value = parameter.minimum
        self._attr_native_max_value = parameter.maximum
        self._attr_native_step = parameter.step
```

In `write.py` `validate`, replace the block from `minimum, maximum, value = ...` to the end of the function with:

```python
    minimum, maximum, step = parameter.minimum, parameter.maximum, parameter.step
    if minimum is None or maximum is None or step is None:
        raise _error("not_writable", name=parameter.label)
    value = float(target)
    if not minimum <= value <= maximum:
        raise _error(
            "out_of_range",
            name=parameter.label,
            value=target,
            min=format_number(minimum),
            max=format_number(maximum),
        )
    steps = (value - minimum) / step
    if not math.isclose(steps, round(steps), abs_tol=1e-6):
        raise _error("invalid_step", name=parameter.label, value=target, step=format_number(step))
```

Run `uv run pytest tests/test_model.py tests/test_write.py -q --no-cov` → PASS. Commit: `git commit -am "fix: numeric inputs without a step width are sensors, no step fallback"`.

- [ ] **Step 4 (finding 9): tabs without BundleId**

Test, append to `tests/test_model.py` (add `import logging` and `import pytest`):

```python
def test_tab_without_bundle_id_is_skipped(
    description: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Polling an invented bundle id can lock the account; such tabs contribute nothing."""
    for tab in description["MenuItems"][0]["TabViews"]:
        if tab["TabName"] == "Warmwasser":
            del tab["BundleId"]
    with caplog.at_level(logging.WARNING):
        parameters = parse_description(description).parameters
    assert 35000900000 not in parameters
    assert "Warmwasser" in caplog.text
```

Run → FAIL.

Implementation in `model.py`: add `import logging` and `_LOGGER = logging.getLogger(__name__)` after the imports; in `walk`, at the top of the `for tab in ...` loop:

```python
for tab in menu.get("TabViews") or []:
    if not tab.get("BundleId"):
        _LOGGER.warning("Tab %s has no BundleId, its parameters are skipped", tab.get("TabName"))
        continue
```

and change `bundle_id=int(tab.get("BundleId") or 1000),` to `bundle_id=int(tab["BundleId"]),`.

Run → PASS. Commit: `git commit -am "fix: skip tabs without a BundleId instead of guessing 1000"`.

- [ ] **Step 5 (finding 16): wolflink issue only for the same account**

Test, append to `tests/test_init.py` (add `from homeassistant.const import CONF_PASSWORD, CONF_USERNAME`):

```python
@pytest.mark.parametrize(
    ("other", "expected"), [("User@Example.com", True), ("other@example.com", False)]
)
async def test_wolflink_issue_only_for_the_same_account(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    other: str,
    expected: bool,
) -> None:
    """Two integrations on one account double the logins; a different account does not."""
    wolflink = MockConfigEntry(domain="wolflink", data={CONF_USERNAME: other, CONF_PASSWORD: "x"})
    wolflink.add_to_hass(hass)
    wolflink.mock_state(hass, ConfigEntryState.LOADED)
    await _setup(hass, mock_config_entry)
    assert bool(ir.async_get(hass).async_get_issue(DOMAIN, "wolflink_active")) is expected
```

Run → FAIL for `other@example.com`.

Implementation in `__init__.py`: call `_check_wolflink(hass, entry.data[CONF_USERNAME])` and change the function to

```python
def _check_wolflink(hass: HomeAssistant, username: str) -> None:
    """Warn when core wolflink logs in with the same account (ADR-Integration-000)."""
    same_account = any(
        e.state is ConfigEntryState.LOADED
        and str(e.data.get(CONF_USERNAME, "")).lower() == username.lower()
        for e in hass.config_entries.async_entries("wolflink")
    )
    if same_account:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "wolflink_active",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="wolflink_active",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, "wolflink_active")
```

Run → PASS. Commit: `git commit -am "fix: raise the wolflink issue only for the same account"`.

- [ ] **Step 6 (finding 18): switch only when writable**

Test, append to `tests/test_model.py`:

```python
def test_known_switch_needs_write_access(description: dict[str, Any]) -> None:
    """A read-only '1x Warmwasser' is an enum sensor, not a switch that always fails."""
    for descriptor in _descriptors(description, 22004200000):
        descriptor["IsReadOnly"] = True
    assert parse_description(description).parameters[22004200000].kind is Kind.ENUM
```

Run → FAIL (`Kind.SWITCH`).

Implementation in `model.py` `kind`: `if self.parameter_id in KNOWN_SWITCHES and self.writable and set(self.options) == {"0", "1"}:`.

Run → PASS. Commit: `git commit -am "fix: known switches need write access, otherwise they are enum sensors"`.

- [ ] **Step 7 (finding 20): redact values of secret parameters**

Test, create `tests/test_record_fixtures.py`:

```python
"""Redaction helpers of the fixture recorder."""

from scripts.record_fixtures import REDACTED, redact_values, secret_value_ids

DESCRIPTION = {
    "MenuItems": [
        {
            "TabViews": [
                {
                    "ParameterDescriptors": [
                        {"ValueId": 1, "ControlType": 21, "Name": "IP Adresse"},
                        {"ValueId": 2, "ControlType": 6, "Name": "ISM Seriennummer"},
                        {"ValueId": 3, "ControlType": 6, "Name": "Kesseltemperatur"},
                        {
                            "ValueId": 4,
                            "ControlType": 13,
                            "Name": "Zeitprogramm",
                            "ChildParameterDescriptors": [
                                {"ValueId": 5, "ControlType": 14, "Name": "Mo"}
                            ],
                        },
                    ]
                }
            ]
        }
    ]
}


def test_secret_value_ids() -> None:
    """Text, IP, date and time inputs plus identifying names, children included."""
    assert secret_value_ids(DESCRIPTION) == {1, 2, 5}


def test_redact_values() -> None:
    """Secret values are blanked, others kept, identifiers replaced."""
    values = {
        "SystemId": 7,
        "Values": [
            {"ValueId": 1, "Value": "10.0.0.1", "State": 1},
            {"ValueId": 3, "Value": "40", "State": 1},
            {"ValueId": 5, "State": 0},
        ],
    }
    assert redact_values(values, {1, 5}) == {
        "SystemId": 1234,
        "Values": [
            {"ValueId": 1, "Value": REDACTED, "State": 1},
            {"ValueId": 3, "Value": "40", "State": 1},
            {"ValueId": 5, "State": 0},
        ],
    }
```

Run → FAIL (ImportError).

Implementation in `scripts/record_fixtures.py`, after `redact_description`:

```python
def secret_value_ids(description: Any) -> set[int]:
    """ValueIds whose values identify the installation (serials, addresses, dates, times)."""
    found: set[int] = set()

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if "ValueId" in node and (
                node.get("ControlType") in SECRET_CONTROL_TYPES
                or SECRET_PARAMETER.search(str(node.get("Name") or ""))
            ):
                found.add(node["ValueId"])
            for value in node.values():
                walk(value)

    walk(description)
    return found


def redact_values(values: dict[str, Any], secret_ids: set[int]) -> dict[str, Any]:
    """Redact identifiers and blank the values of secret parameters."""
    result = redact_ids(values)
    for item in result.get("Values") or []:
        if item.get("ValueId") in secret_ids and item.get("Value") is not None:
            item["Value"] = REDACTED
    return result
```

and in `record` replace `write(target / f"values_{index}.json", redact_ids(raw_values))` with `write(target / f"values_{index}.json", redact_values(raw_values, secret_value_ids(description)))`.

Run → PASS. Also run `./scripts/check-fixtures.sh` → exit 0. Commit: `git add scripts/record_fixtures.py tests/test_record_fixtures.py && git commit -m "fix: blank values of identifying parameters when recording fixtures"`.

- [ ] **Step 8 (findings 21 and 22): dead code and duplicate placeholder check**

Test, append to `tests/test_sensor.py`:

```python
from custom_components.wolf_smartset.entity import parse_number


@pytest.mark.parametrize(
    ("raw", "expected"), [("20,5", 20.5), ("20.5", 20.5), ("abc", None), (None, None)]
)
def test_parse_number(raw: str | None, expected: float | None) -> None:
    """Only the conversion; placeholders are filtered by WolfEntity.raw_value."""
    assert parse_number(raw) == expected
```

(move the import to the import block). Run → PASS already; it pins the new contract.

Implementation: in `sensor.py` remove `CT_HIDDEN` from the `.model` import and from `_numeric`:

```python
        self._numeric = parameter.unit is not None or parameter.control_type == CT_NUMERIC
```

In `entity.py` replace `parse_number` with:

```python
def parse_number(raw: str | None) -> float | None:
    """Portal values are strings with '.' or ',' as the decimal separator."""
    if raw is None:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None
```

Run `uv run pytest tests/test_sensor.py tests/test_init.py tests/test_write.py -q --no-cov` → PASS. Commit: `git commit -am "refactor: drop the dead hidden-type branch and the duplicate placeholder check"`.

- [ ] **Step 9 (finding 24): signed zero and unparsable numbers**

Tests, append to `tests/test_write.py` (add `from custom_components.wolf_smartset.write import format_number`):

```python
def test_format_number_normalises_signed_zero() -> None:
    """-0.0 would be sent as '-0'."""
    assert format_number(-0.0) == "0"
    assert format_number(0.0) == "0"
    assert format_number(20.5) == "20.5"


async def test_undo_of_an_unparsable_value_is_a_validation_error(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    """A corrupt old value raises a translated error instead of ValueError."""
    hass_storage[f"{DOMAIN}.{mock_config_entry.entry_id}.history"] = {
        "version": 1,
        "key": f"{DOMAIN}.{mock_config_entry.entry_id}.history",
        "data": {
            "history": [
                {
                    "result": "ok",
                    "system_id": 1234,
                    "parameter_id": DHW_SETPOINT,
                    "value_id": DHW_SETPOINT,
                    "label": "x",
                    "old": "abc",
                    "new": "55",
                    "source": "entity",
                }
            ]
        },
    }
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    button = er.async_get(hass).async_get_entity_id("button", DOMAIN, "1234_undo")
    assert button
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert err.value.translation_key == "invalid_number"
```

Run → FAIL.

Implementation in `write.py`:

```python
def format_number(value: float) -> str:
    """48.0 -> '48', 20.5 -> '20.5' (the portal sends plain decimal strings)."""
    if value == 0:
        value = 0.0  # never '-0'
    return f"{value:.6f}".rstrip("0").rstrip(".")
```

and in `validate` replace `value = float(target)` with

```python
    try:
        value = float(target.replace(",", "."))
    except ValueError:
        raise _error("invalid_number", name=parameter.label, value=target) from None
```

Add to `translations/en.json` under `exceptions`: `"invalid_number": {"message": "{value} is not a number for {name}."}` and to `de.json`: `"invalid_number": {"message": "{value} ist keine Zahl für {name}."}`.

Run → PASS. Commit: `git commit -am "fix: translated error for unparsable numbers, no signed zero"`.

- [ ] **Step 10: Review document status**

In `docs/reviews/2026-10-25-write-pipeline.md`, append a section:

```markdown
## Status after the remediation branch

| Finding | Status |
|---|---|
| 1, 7 | fixed in c31b7b0 (ADR-Writes-013) |
| 2 | recording in place (T1); fixture and validation pending the owner's approved write |
| 3, 17 | fixed (ADR-Client-014) |
| 4, 11, 19 | fixed (README, de.json, brand assets) |
| 5, 6, 8, 9, 16, 18, 20, 21, 22, 24 | fixed (T4, one commit each) |
| 10 | void: `NumberSelector.__call__` already refuses values outside min and max (`InvalidData`); the review's trace missed it. Regression tests in T3 pin it. |
| 12, 13, 14, 15 | fixed (T3, coverage gate 95 %) |
| 23 | void: git shows every ADR was created on its stated date |
| 25 | accepted: one state request per interval while all entities are disabled |
```

- [ ] **Step 11: Run the gates and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy custom_components/ && uv run bandit -c pyproject.toml -r custom_components/ && uv run pytest -q && ./scripts/check-fixtures.sh`
Expected: all pass

```bash
git add docs/reviews/2026-10-25-write-pipeline.md
git commit -m "docs: status of the review findings after the remediation branch"
```

```json:metadata
{"files": ["custom_components/wolf_smartset/write.py", "custom_components/wolf_smartset/model.py", "custom_components/wolf_smartset/number.py", "custom_components/wolf_smartset/__init__.py", "custom_components/wolf_smartset/sensor.py", "custom_components/wolf_smartset/entity.py", "custom_components/wolf_smartset/translations/en.json", "custom_components/wolf_smartset/translations/de.json", "scripts/record_fixtures.py", "tests/test_record_fixtures.py", "tests/test_write.py", "tests/test_model.py", "tests/test_init.py", "tests/test_sensor.py", "docs/reviews/2026-10-25-write-pipeline.md"], "verifyCommand": "uv run pytest -q && ./scripts/check-fixtures.sh", "acceptanceCriteria": ["unknown AccessLevel refuses writes with access_denied", "hourly limit counted from history records ok/not_applied of the last hour, survives reload, ignores records without time, _writes removed", "numeric parameter without StepWidth is a sensor, no or-1.0 fallback", "tab without BundleId skipped with a warning, no 1000 fallback", "wolflink_active only for the same username", "read-only known switch is an enum sensor", "secret_value_ids and redact_values exist, applied to values json, unit-tested", "CT_HIDDEN removed from sensor.py, parse_number only converts", "format_number(-0.0) == '0', invalid_number error in en and de", "review document carries the status table"], "modelTier": "standard"}
```

---

### Task 5: Documentation and brand assets

**Goal:** A first-time user can install, configure, enable writing, understand the risks and remove the integration from the README alone; German users see a German config flow and repair issues; the integration shows an icon.

**Files:**
- Modify: `README.md`
- Modify: `custom_components/wolf_smartset/translations/de.json`
- Create: `scripts/brand_icon.py`
- Create: `custom_components/wolf_smartset/brand/icon.png`, `custom_components/wolf_smartset/brand/icon@2x.png`

**Acceptance Criteria:**
- [ ] `README.md` has the sections Installation, Configuration, Options, Entities disabled by default, Writing, Removal, Known limitations, Troubleshooting, in that order after the intro, with the content below.
- [ ] `de.json` has `config` (steps `user`, `systems`, `reauth_confirm`; `error`; `abort`) and `issues` (`throttled`, `wolflink_active`) with exactly the keys of `en.json`.
- [ ] `brand/icon.png` is 256×256 and `brand/icon@2x.png` 512×512, PNG, no Wolf logo; `scripts/brand_icon.py` regenerates them.
- [ ] `uv run python -c "import json; a=json.load(open('custom_components/wolf_smartset/translations/en.json')); b=json.load(open('custom_components/wolf_smartset/translations/de.json')); assert set(a['config']['error'])==set(b['config']['error']); assert set(a['config']['abort'])==set(b['config']['abort']); assert set(a['issues'])==set(b['issues'])"` exits 0.

**Verify:** the command above, plus `uv run pytest -q` (translations are loaded by the tests) and `uv run python -c "from PIL import Image; assert Image.open('custom_components/wolf_smartset/brand/icon.png').size == (256, 256); assert Image.open('custom_components/wolf_smartset/brand/icon@2x.png').size == (512, 512)"`

**Steps:**

- [ ] **Step 1: README**

Replace the first paragraph block of `README.md` (everything before `## Entities disabled by default`) with:

```markdown
# Wolf SmartSet (read/write) for Home Assistant

Custom integration for Wolf heating systems connected to the Wolf SmartSet cloud. It uses the same unofficial interface as the SmartSet portal and app. It reads every parameter of the system and can write settings such as the DHW setpoint, the operating mode or "1x Warmwasser". Writing is off until you switch off the dry run.

Wolf does not support third-party access. Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Installation

1. In HACS open *Integrations*, then the three-dot menu, then *Custom repositories*. Add `https://github.com/tibuntu/homeassistant-wolf-smartset` with category *Integration*.
2. Install "Wolf SmartSet (read/write)" and restart Home Assistant.
3. If the core integration "Wolf SmartSet Service" (`wolflink`) is set up for the same account, disable it first: Settings › Devices & services › Wolf SmartSet Service › three-dot menu › *Disable*. Two integrations on one account log in from the same IP address, and Wolf blocks the address for up to an hour after too many logins. The block also hits the SmartSet app.
4. Settings › Devices & services › *Add integration* › "Wolf SmartSet (read/write)".

## Configuration

The integration asks for the username and password of your Wolf SmartSet account (the password has at most 30 characters, the portal silently truncates longer ones). It lists the systems of the account; with more than one you choose which to add. One entry per account; a second account is a second entry.

When the portal rejects the password later, Home Assistant shows a re-authentication prompt for the entry.

## Options

Settings › Devices & services › Wolf SmartSet › *Configure*:

| Option | Default | Meaning |
|---|---|---|
| Poll interval | 120 s | Seconds between polls, 60 to 3600. Wolf allows at most one poll per minute. |
| Dry run | on | While on, changes are only logged at INFO with parameter, old and new value; nothing is sent to the heating system. |
| Maximum writes per hour | 20 | Rolling limit for real writes, 1 to 60. Skipped writes (value already set) and dry runs do not count. |
```

Replace the existing `## Writing` section with:

```markdown
## Writing

Every write ends up in the non-volatile memory (EEPROM) of the Wolf controller. The integration therefore runs every change through one pipeline ([ADR-Writes-013](docs/adr/ADR-Writes-013-write-pipeline-with-explicit-confirmation.md)):

- **Dry run, on by default.** Changes are only logged at INFO. Switch it off under *Configure* when you have checked the log and want real writes.
- **No-op suppression.** A value that is already set is not sent again.
- **Validation** against min, max, step and list options from the Wolf description; read-only parameters and accounts without write access are refused.
- **Rate limit**, 20 writes per hour by default, configurable.
- **One write at a time.**
- **Optimistic state with confirmation.** The new value shows immediately. The first poll at least 30 s after the write confirms it (`confirmed: true` in the history) or restores the value the controller reports (`confirmed: false`, a warning in the log).
- **History** of the last 200 attempts in `.storage/wolf_smartset.<entry_id>.history`, the last 50 in the diagnostics; an **Undo last change** button.
- **Login backoff.** After a failed login the integration waits five minutes, doubling up to an hour, before it logs in again ([ADR-Client-014](docs/adr/ADR-Client-014-login-backoff.md)).

Expert (Fachmann) parameters are written without an expert login. Whether the controller applies them is unproven; the history shows `confirmed: false` when it does not. Wrong settings, in particular expert parameters, can make the system inefficient or uncomfortable. Use at your own risk.

The integration never writes on its own. Writes come from your actions in the UI, from automations and from the undo button.

## Removal

Settings › Devices & services › Wolf SmartSet › three-dot menu › *Delete*. This removes the entry, its devices and entities. The write history `.storage/wolf_smartset.<entry_id>.history` stays behind; delete it by hand if you want it gone. Re-enable the core "Wolf SmartSet Service" integration afterwards if you still need it.

## Known limitations

- Time programs, dates, times, party and holiday mode are not mapped yet ([concept](docs/time-programs.md)).
- Entity names are Wolf's German labels, the same as in the SmartSet app and the manuals.
- The interface is unofficial. Wolf changes the login flow several times a year; a broken login shows as "portal unavailable" until a fix is released.
- Only one installation (Wolf CHA heat pump with BM-2 and MM1, Link home gateway) has been tested so far.

## Troubleshooting

- **Repair issue "throttles"**: the portal answered several polls with throttling or empty responses. The integration polls less often until the portal answers again. Check that no other client logs in with this account from your network.
- **Repair issue "core integration is active"**: disable the core integration for the same account (see Installation).
- **Re-authentication prompt**: the portal rejected the password. Enter the current one.
- **Diagnostics**: Settings › Devices & services › Wolf SmartSet › three-dot menu › *Download diagnostics*. The file contains the parsed parameter model, the write history and login statistics, with credentials and identifiers redacted.
- **A write shows "not applied"**: the controller reported another value after the write. Expert parameters may need an expert session; user-level parameters may be limited by a dependent setting in the controller.

The icon under `brand/` is a neutral placeholder. An entry in [home-assistant/brands](https://github.com/home-assistant/brands) is a follow-up.
```

Keep `## Entities disabled by default` as it is between Options and Writing.

- [ ] **Step 2: German translations**

Replace `custom_components/wolf_smartset/translations/de.json` with:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Wolf-SmartSet-Konto",
        "description": "Nutzt dieselbe inoffizielle Cloud-Schnittstelle wie das SmartSet-Portal. Deaktiviere die Core-Integration Wolf SmartSet Service für dieses Konto, um doppelte Logins zu vermeiden.",
        "data": {
          "username": "Benutzername",
          "password": "Passwort"
        },
        "data_description": {
          "username": "Der Benutzername deines Wolf-SmartSet-Kontos.",
          "password": "Das Passwort deines Wolf-SmartSet-Kontos (höchstens 30 Zeichen)."
        }
      },
      "systems": {
        "title": "Systeme auswählen",
        "data": {
          "systems": "Systeme"
        }
      },
      "reauth_confirm": {
        "title": "Wolf SmartSet erneut anmelden",
        "description": "Wolf SmartSet hat das Passwort von {username} abgelehnt.",
        "data": {
          "password": "Passwort"
        }
      }
    },
    "error": {
      "invalid_auth": "Ungültiger Benutzername oder ungültiges Passwort.",
      "cannot_connect": "Verbindung zu Wolf SmartSet fehlgeschlagen.",
      "portal_unavailable": "Das Wolf-SmartSet-Portal ist nicht erreichbar oder blockiert diese IP-Adresse vorübergehend. Versuche es in einer Stunde erneut.",
      "password_too_long": "Wolf SmartSet akzeptiert höchstens 30 Zeichen.",
      "no_system_selected": "Wähle mindestens ein System aus.",
      "unknown": "Unerwarteter Fehler."
    },
    "abort": {
      "already_configured": "Dieses Konto ist bereits eingerichtet.",
      "no_systems": "Das Konto hat keine Wolf-Systeme.",
      "reauth_successful": "Die erneute Anmeldung war erfolgreich."
    }
  },
  "options": {
    "step": {
      "init": {
        "data": {
          "scan_interval": "Abfrageintervall",
          "dry_run": "Probelauf (nicht schreiben)",
          "max_writes_per_hour": "Maximale Schreibvorgänge pro Stunde"
        },
        "data_description": {
          "scan_interval": "Sekunden zwischen zwei Abfragen. Wolf erlaubt höchstens eine Abfrage pro Minute.",
          "dry_run": "Solange aktiv, werden Änderungen nur protokolliert (INFO) mit Parameter, altem und neuem Wert; an die Heizung wird nichts gesendet.",
          "max_writes_per_hour": "Schützt das EEPROM der Regelung vor Automationsschleifen. Übersprungene Schreibvorgänge mit unverändertem Wert zählen nicht."
        }
      }
    }
  },
  "exceptions": {
    "not_writable": {
      "message": "{name} ist nicht beschreibbar."
    },
    "access_denied": {
      "message": "Das Wolf-SmartSet-Konto hat für {name} kein Schreibrecht."
    },
    "invalid_option": {
      "message": "{value} ist keine gültige Auswahl für {name}."
    },
    "out_of_range": {
      "message": "{value} liegt außerhalb des Bereichs von {name} ({min} bis {max})."
    },
    "invalid_step": {
      "message": "{value} passt nicht zur Schrittweite {step} von {name}."
    },
    "rate_limited": {
      "message": "Grenze von {limit} Schreibvorgängen pro Stunde erreicht. Die Grenze lässt sich in den Optionen der Integration ändern."
    },
    "write_failed": {
      "message": "Schreiben von {name} fehlgeschlagen: {error}"
    },
    "nothing_to_undo": {
      "message": "Es gibt keine übernommene Änderung zum Rückgängigmachen."
    }
  },
  "issues": {
    "throttled": {
      "title": "Wolf SmartSet drosselt {system}",
      "description": "Wolf SmartSet hat mehrere Abfragen mit Drosselung oder leeren Antworten beantwortet. Die Integration fragt seltener ab, bis das Portal wieder antwortet. Prüfe, ob ein anderer Client sich mit diesem Konto aus deinem Netz anmeldet."
    },
    "wolflink_active": {
      "title": "Core-Integration Wolf SmartSet Service ist aktiv",
      "description": "Die Core-Integration Wolf SmartSet Service ist ebenfalls geladen. Beide melden sich von derselben IP-Adresse an, was Wolf dazu bringen kann, die Adresse bis zu einer Stunde zu sperren, auch für die SmartSet-App. Deaktiviere die Core-Integration, wenn sie dasselbe Konto nutzt."
    }
  },
  "entity": {
    "button": {
      "undo": {
        "name": "Letzte Änderung rückgängig"
      }
    }
  }
}
```

Task 4 adds `invalid_number` to `exceptions` in both files; if Task 4 already ran, keep its key.

Run the key-set check from the acceptance criteria → exit 0.

- [ ] **Step 3: Brand icon**

Create `scripts/brand_icon.py`:

```python
"""Generate the neutral brand icon (no Wolf trademark) under custom_components/wolf_smartset/brand/.

Home Assistant serves custom_components/<domain>/brand/icon.png (256 px) and icon@2x.png (512 px)
when they exist. Run once: uv run python scripts/brand_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

BRAND = Path(__file__).resolve().parents[1] / "custom_components" / "wolf_smartset" / "brand"
BACKGROUND = (31, 58, 95, 255)  # dark blue
FOREGROUND = (255, 255, 255, 255)


def draw(size: int) -> Image.Image:
    """A rounded square with a white drop: heat and water, nothing branded."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)
    canvas.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 6, fill=BACKGROUND)
    cx, cy, r = size / 2, size * 0.6, size * 0.22
    canvas.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FOREGROUND)
    canvas.polygon(
        [(cx, size * 0.14), (cx - r * 0.95, cy - r * 0.35), (cx + r * 0.95, cy - r * 0.35)],
        fill=FOREGROUND,
    )
    return image


if __name__ == "__main__":
    BRAND.mkdir(exist_ok=True)
    draw(256).save(BRAND / "icon.png")
    draw(512).save(BRAND / "icon@2x.png")
    print(f"written to {BRAND}")
```

Run: `uv run python scripts/brand_icon.py` and the Pillow size check from **Verify**.
Expected: two files, sizes 256 and 512.

- [ ] **Step 4: Run the gates and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` and the de.json key-set check.
Expected: all pass

```bash
git add README.md custom_components/wolf_smartset/translations/de.json scripts/brand_icon.py custom_components/wolf_smartset/brand/icon.png custom_components/wolf_smartset/brand/icon@2x.png
git commit -m "docs: installation, options, writing, removal and troubleshooting; German config flow; brand icon"
```

```json:metadata
{"files": ["README.md", "custom_components/wolf_smartset/translations/de.json", "scripts/brand_icon.py", "custom_components/wolf_smartset/brand/icon.png", "custom_components/wolf_smartset/brand/icon@2x.png"], "verifyCommand": "uv run pytest -q && uv run python -c \"import json; a=json.load(open('custom_components/wolf_smartset/translations/en.json')); b=json.load(open('custom_components/wolf_smartset/translations/de.json')); assert set(a['config']['error'])==set(b['config']['error']); assert set(a['config']['abort'])==set(b['config']['abort']); assert set(a['issues'])==set(b['issues'])\"", "acceptanceCriteria": ["README has Installation, Configuration, Options, Entities disabled by default, Writing, Removal, Known limitations, Troubleshooting in that order", "de.json has config (user, systems, reauth_confirm, error, abort) and issues with the keys of en.json", "brand/icon.png 256x256 and icon@2x.png 512x512 generated by scripts/brand_icon.py, no Wolf logo"], "modelTier": "mechanical"}
```

---

## After the last task

1. Final whole-branch review, then a pull request `review-2026-10-25` → `main` so hassfest and HACS validation run in CI.
2. Owner's step after the merge: switch the dry run off, perform one approved write, download the diagnostics, store `writes.history[-1].response` as `tests/fixtures/real/write_response_0.json`, run `scripts/check-fixtures.sh`. Then decide how the body is interpreted (new ADR), which closes finding 2 and removes the last `xfail` test.

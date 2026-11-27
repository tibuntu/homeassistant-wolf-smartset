"""Fault entities from ReadFaultMessages (ADR-Polling-019)."""

import copy
from datetime import timedelta
import json
from pathlib import Path
import re
import time
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import httpx
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.wolf_smartset.api import (
    ApiError,
    AuthError,
    NoSession,
    TooManyRequests,
    WolfClient,
)
from custom_components.wolf_smartset.const import CONF_SCAN_INTERVAL, DOMAIN, FAULT_INTERVAL

from .conftest import FAULTS
from .test_api import SYSTEM, FakePortal

ROOT = Path(__file__).parent.parent
OUTSIDE = "1234_27000500001"  # a value sensor (outside temperature)
CURRENT = {
    "Id": 1234,
    "ErrorCode": 107,
    "Description": "Druck Heizkreis",
    "OccurTimeLocal": "2026-11-21T15:00:00",
    "Active": True,
    "Index": 0,
    "Device": "**REDACTED**",
}
IDENTIFIERS = {"Device", "SystemName", "Id", "SystemId", "GatewayId"}


@pytest.fixture
def portal() -> FakePortal:
    """Fresh fake portal."""
    return FakePortal()


@pytest.fixture
async def client(portal: FakePortal):
    """Client wired to the fake portal."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        yield WolfClient(http, "user", portal.password)


async def _value_poll(client: WolfClient, portal: FakePortal) -> None:
    """Login and session come from a value request, as in the integration."""
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    await client.get_systems()


async def test_request_path_and_payload(client: WolfClient, portal: FakePortal) -> None:
    """POST ReadFaultMessages with the browser's body: no SessionId, existing token."""
    seen: list[httpx.Request] = []

    def faults(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=FAULTS)

    portal.api["ReadFaultMessages"] = faults
    await _value_poll(client, portal)
    assert await client.read_fault_messages(SYSTEM) == FAULTS
    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == "/portal/api/portal/ReadFaultMessages"
    assert json.loads(request.content) == {"LastRead": None, "GatewayId": 2, "SystemId": 1}
    assert request.headers["Authorization"] == "Bearer t1"
    assert portal.calls == ["CreateSession2", "GetSystemList", "ReadFaultMessages"]
    assert portal.logins == 1


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [(401, {}, ApiError), (429, {}, TooManyRequests), (200, {"ErrorCode": 1}, ApiError)],
)
async def test_failed_read_is_not_retried_and_logs_in_no_further(
    client: WolfClient, portal: FakePortal, status: int, body: dict, error: type[Exception]
) -> None:
    """401, throttling or a lost session: one request, no new login, token kept."""
    portal.api["ReadFaultMessages"] = lambda r: httpx.Response(status, json=body)
    await _value_poll(client, portal)
    for _ in range(3):
        with pytest.raises(error):
            await client.read_fault_messages(SYSTEM)
    assert portal.calls.count("ReadFaultMessages") == 3
    assert portal.logins == 1
    assert client.login_blocked_seconds == 0


async def test_no_request_without_token_or_session(client: WolfClient, portal: FakePortal) -> None:
    """Before any value request there is no token: nothing is sent, nobody logs in."""
    for _ in range(3):
        with pytest.raises(NoSession):
            await client.read_fault_messages(SYSTEM)
    assert portal.requests == 0


async def test_no_login_after_password_change_and_token_expiry(
    client: WolfClient, portal: FakePortal
) -> None:
    """Changed password, expired token: fault reads send no login POST and no request."""
    await _value_poll(client, portal)
    portal.password = "changed"
    client._token_expires = time.monotonic() - 1
    before = portal.requests
    for _ in range(5):
        with pytest.raises(NoSession):
            await client.read_fault_messages(SYSTEM)
    assert portal.requests == before
    assert portal.logins == 1


async def test_no_request_without_session(client: WolfClient, portal: FakePortal) -> None:
    """A valid token without a session: no CreateSession2, no request."""
    await _value_poll(client, portal)
    client._session_id = None
    before = portal.requests
    with pytest.raises(NoSession):
        await client.read_fault_messages(SYSTEM)
    assert portal.requests == before


async def test_no_session_refresh(client: WolfClient, portal: FakePortal) -> None:
    """A session older than the refresh interval is not refreshed by the fault read."""
    portal.api["ReadFaultMessages"] = lambda r: httpx.Response(200, json=FAULTS)
    await _value_poll(client, portal)
    client._session_refreshed -= 3600
    await client.read_fault_messages(SYSTEM)
    assert "UpdateSession" not in portal.calls


def test_cadence_is_ten_minutes() -> None:
    """Fixed, not an option (owner decision 2026-11-21)."""
    assert timedelta(minutes=10) == FAULT_INTERVAL


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> tuple[str, str]:
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    fault = registry.async_get_entity_id("binary_sensor", DOMAIN, "1234_fault")
    code = registry.async_get_entity_id("sensor", DOMAIN, "1234_fault_code")
    assert fault and code
    return fault, code


async def test_recorded_response_no_current_fault(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Recording: no current fault, the newest history entry in the last_fault attributes."""
    fault, code = await _setup(hass, mock_config_entry)
    assert hass.states.get(fault).state == STATE_OFF
    assert hass.states.get(fault).attributes["device_class"] == "problem"
    state = hass.states.get(code)
    assert state.state == STATE_UNKNOWN
    attributes = {k: v for k, v in state.attributes.items() if k not in ("friendly_name", "icon")}
    assert attributes == {
        "description": None,
        "occurred": None,
        "last_fault_code": 107,
        "last_fault_description": "Druck Heizkreis",
        "last_fault_occurred": "2026-03-09T18:05:18",
        "last_fault_ended": "2026-03-09T18:08:19",
    }
    mock_client.read_fault_messages.assert_called_with(mock_client.get_systems.return_value[0])


@pytest.mark.parametrize("occurred", ["2026-11-21T15:00:00", None])
async def test_current_fault(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    occurred: str | None,
) -> None:
    """A current fault turns the problem sensor on; a missing OccurTimeLocal is tolerated."""
    current = dict(CURRENT)
    if occurred is None:
        del current["OccurTimeLocal"]
    faults = copy.deepcopy(FAULTS)
    faults["CurrentMessages"] = [current, CURRENT | {"ErrorCode": 119, "Index": 1}]
    mock_client.read_fault_messages.return_value = faults
    fault, code = await _setup(hass, mock_config_entry)
    assert hass.states.get(fault).state == STATE_ON
    state = hass.states.get(code)
    assert state.state == "107"
    assert state.attributes["description"] == "Druck Heizkreis"
    assert state.attributes["occurred"] == occurred
    assert not IDENTIFIERS & set(state.attributes)
    assert not IDENTIFIERS & set(hass.states.get(fault).attributes)


async def test_missing_lists_are_tolerated(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A response without the lists reads as no fault and no history."""
    mock_client.read_fault_messages.return_value = {"MessagesChanged": True}
    fault, code = await _setup(hass, mock_config_entry)
    assert hass.states.get(fault).state == STATE_OFF
    assert hass.states.get(code).attributes["last_fault_code"] is None


async def test_failed_fault_read_keeps_value_entities(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A fault read failing at a 10-minute tick leaves the value coordinator untouched.

    The poll interval is 420 s, so no value poll runs at the 600 s tick and none can
    hide a leak into the value coordinator (backoff, interval, update error).
    """
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_SCAN_INTERVAL: 420})
    fault, code = await _setup(hass, mock_config_entry)
    outside = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, OUTSIDE)
    assert outside
    values = mock_config_entry.runtime_data.coordinators[1234]
    assert hass.states.get(fault).state == STATE_OFF
    polls = mock_client.get_system_state.call_count

    freezer.tick(timedelta(seconds=420))  # the value poll, before the fault tick
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_system_state.call_count == polls + 1
    mock_client.read_fault_messages.side_effect = TooManyRequests("ReadFaultMessages")
    freezer.tick(FAULT_INTERVAL - timedelta(seconds=420))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == 2
    assert mock_client.get_system_state.call_count == polls + 1  # no value poll at 600 s
    assert hass.states.get(fault).state == STATE_UNAVAILABLE
    assert hass.states.get(code).state == STATE_UNAVAILABLE
    assert hass.states.get(outside).state != STATE_UNAVAILABLE
    assert values.last_update_success
    assert values.backoff_steps == 0
    assert values.update_interval == timedelta(seconds=420)

    mock_client.read_fault_messages.side_effect = None
    freezer.tick(FAULT_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == 3
    assert hass.states.get(fault).state == STATE_OFF


async def test_expired_session_keeps_last_fault_data(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A token that expired since the last value poll keeps the fault entities.

    Live 2026-11-21..23: the fault tick fell between token expiry and the next value
    poll once an hour, and both entities went unavailable for 10 minutes.
    """
    fault, code = await _setup(hass, mock_config_entry)
    mock_client.read_fault_messages.side_effect = NoSession("ReadFaultMessages")
    freezer.tick(FAULT_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == 2
    assert hass.states.get(fault).state == STATE_OFF
    assert hass.states.get(code).attributes["last_fault_code"] == 107

    runtime = mock_config_entry.runtime_data
    runtime.coordinators[1234].last_update_success = False  # no healthy value poll
    await runtime.faults[1234].async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(fault).state == STATE_UNAVAILABLE


async def test_no_fault_read_after_auth_failure(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After the value poll's auth failure, fault reads send nothing; one reauth flow."""
    await _setup(hass, mock_config_entry)
    reads = mock_client.read_fault_messages.call_count
    mock_client.get_system_state.side_effect = AuthError("login form shown again")
    # The value poll fails first (120 s), as in practice; one tick firing both
    # coordinators would leave their order to the event loop.
    freezer.tick(timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    for _ in range(4):
        freezer.tick(FAULT_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == reads
    (flow,) = mock_config_entry.async_get_active_flows(hass, {SOURCE_REAUTH})
    assert not mock_config_entry.runtime_data.faults[1234].last_update_success

    # The user dismisses the reauth flow: the value poll stays stopped, so do the reads.
    hass.config_entries.flow.async_abort(flow["flow_id"])
    for _ in range(2):
        freezer.tick(FAULT_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert not list(mock_config_entry.async_get_active_flows(hass, {SOURCE_REAUTH}))
    assert mock_client.read_fault_messages.call_count == reads


async def test_no_fault_read_while_reauth_flow_is_open(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A reauth flow started elsewhere (config flow, another system) pauses the read too."""
    await _setup(hass, mock_config_entry)
    reads = mock_client.read_fault_messages.call_count
    mock_config_entry.async_start_reauth(hass)
    await hass.async_block_till_done()
    freezer.tick(FAULT_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == reads


async def test_reads_every_ten_minutes_and_pauses_while_throttled(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """One read per 10 minutes, none while the value poll backs off, none after unload."""
    fault, _ = await _setup(hass, mock_config_entry)
    faults = mock_config_entry.runtime_data.faults[1234]
    assert faults.update_interval == timedelta(minutes=10)
    assert mock_client.read_fault_messages.call_count == 1
    freezer.tick(timedelta(minutes=9))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == 1
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == 2

    # The value poll is throttled and backs off; the fault read adds no request.
    mock_client.get_system_state.side_effect = TooManyRequests("GetSystemStateList")
    freezer.tick(FAULT_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_config_entry.runtime_data.coordinators[1234].backoff_steps
    reads = mock_client.read_fault_messages.call_count
    freezer.tick(FAULT_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == reads
    assert hass.states.get(fault).state == STATE_UNAVAILABLE

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    freezer.tick(FAULT_INTERVAL * 3)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == reads


def test_no_commit_or_destination_endpoint() -> None:
    """CommitFaultMessage and the FaultMessageDestination endpoints are never called.

    CommitFaultMessageEntries is a response field and allowed.
    """
    forbidden = re.compile(r"CommitFaultMessage(?!Entries)|FaultMessageDestination")
    files = [*(ROOT / "custom_components").rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]
    files += [p for p in (ROOT / "tests").rglob("*.py") if p.name != "test_faults.py"]
    assert files
    hits = [str(p) for p in files if forbidden.search(p.read_text(encoding="utf-8"))]
    assert hits == []

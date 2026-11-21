"""Fault entities from ReadFaultMessages (ADR-Polling-019)."""

import copy
from datetime import timedelta
import json
from pathlib import Path
import re
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.wolf_smartset.api import ApiError, TooManyRequests, WolfClient
from custom_components.wolf_smartset.const import DOMAIN, FAULT_INTERVAL

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


async def test_request_path_and_payload(client: WolfClient, portal: FakePortal) -> None:
    """POST ReadFaultMessages with the browser's body: no SessionId, existing token."""
    seen: list[httpx.Request] = []

    def faults(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=FAULTS)

    portal.api["ReadFaultMessages"] = faults
    assert await client.read_fault_messages(SYSTEM) == FAULTS
    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == "/portal/api/portal/ReadFaultMessages"
    assert json.loads(request.content) == {"LastRead": None, "GatewayId": 2, "SystemId": 1}
    assert request.headers["Authorization"] == "Bearer t1"
    assert portal.calls == ["CreateSession2", "ReadFaultMessages"]
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
    for _ in range(3):
        with pytest.raises(error):
            await client.read_fault_messages(SYSTEM)
    assert portal.calls.count("ReadFaultMessages") == 3
    assert portal.logins == 1
    assert client.login_blocked_seconds == 0


def test_cadence_is_ten_minutes() -> None:
    """Fixed, not an option (owner decision 2026-11-21)."""
    assert timedelta(minutes=10) == FAULT_INTERVAL


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> tuple[str, str]:
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
    """Only the two fault entities go unavailable; they recover on the next read."""
    mock_client.read_fault_messages.side_effect = TooManyRequests("ReadFaultMessages")
    fault, code = await _setup(hass, mock_config_entry)
    outside = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, OUTSIDE)
    assert outside
    assert hass.states.get(fault).state == STATE_UNAVAILABLE
    assert hass.states.get(code).state == STATE_UNAVAILABLE
    assert hass.states.get(outside).state != STATE_UNAVAILABLE
    coordinator = mock_config_entry.runtime_data.coordinators[1234]
    assert coordinator.last_update_success and coordinator.backoff_steps == 0
    assert mock_client.read_fault_messages.call_count == 1

    mock_client.read_fault_messages.side_effect = None
    freezer.tick(FAULT_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.read_fault_messages.call_count == 2
    assert hass.states.get(fault).state == STATE_OFF


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

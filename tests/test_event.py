"""Write-result event entity: one event per write attempt, except no-ops."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.wolf_smartset.api import ApiError, Value
from custom_components.wolf_smartset.const import CONF_DRY_RUN, CONF_MAX_WRITES_PER_HOUR, DOMAIN

from .conftest import SYSTEM
from .test_write import DHW_SETPOINT, _set_setpoint, _setup

EXPECTED = {
    "label": "Warmwassersolltemperatur eingestellt",
    "parameter_id": DHW_SETPOINT,
    "old": "50",
    "new": "55",
    "source": "entity",
}


def _event_id(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("event", DOMAIN, f"{SYSTEM.id}_write")
    assert entity_id
    return entity_id


def _event(hass: HomeAssistant) -> dict[str, Any]:
    state = hass.states.get(_event_id(hass))
    assert state and state.state != STATE_UNKNOWN
    return dict(state.attributes)


def _assert_event(hass: HomeAssistant, event_type: str, **extra: Any) -> None:
    attributes = _event(hass)
    assert attributes["event_type"] == event_type
    assert {k: attributes.get(k) for k in [*EXPECTED, *extra]} == {**EXPECTED, **extra}
    assert "error" in extra or "error" not in attributes


async def test_dry_run_event(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A number change in dry run (the default) fires dry_run with old and new value."""
    await _setup(hass, mock_config_entry)
    await _set_setpoint(hass, 55)
    _assert_event(hass, "dry_run")


async def test_ok_event(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A write sent to the portal fires ok."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 55)
    _assert_event(hass, "ok")


@pytest.mark.parametrize(("read_back", "event_type"), [("55", "confirmed"), ("50", "not_applied")])
async def test_confirmed_and_not_applied_events(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    read_back: str,
    event_type: str,
) -> None:
    """The poll that decides the write fires confirmed or not_applied."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 55)
    mock_client.get_values.side_effect = lambda system, bundle, ids, first=False: [
        Value(i, read_back if i == DHW_SETPOINT else "0", 1) for i in ids
    ]
    for _ in range(3):  # 360 s: past the 300 s settle window at the default 120 s interval
        freezer.tick(timedelta(seconds=120))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    _assert_event(hass, event_type)


async def test_rate_limited_event(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A write over the hourly limit fires rate_limited."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 1})
    await _set_setpoint(hass, 51)
    with pytest.raises(HomeAssistantError):
        await _set_setpoint(hass, 55)
    _assert_event(hass, "rate_limited", old="51")


async def test_error_event(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A failed write fires error with the error text."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    mock_client.write_value = AsyncMock(side_effect=ApiError(4, "offline"))
    with pytest.raises(HomeAssistantError):
        await _set_setpoint(hass, 55)
    _assert_event(hass, "error", error=str(ApiError(4, "offline")))


async def test_unchanged_fires_nothing(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Re-asserting the current value must not fill the logbook."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 50)
    assert mock_config_entry.runtime_data.writer.history[-1]["result"] == "unchanged"
    state = hass.states.get(_event_id(hass))
    assert state and state.state == STATE_UNKNOWN


async def test_no_identifier_in_attributes(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """System and gateway ID stay out of the event, as in the diagnostics."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    mock_client.write_value = AsyncMock(side_effect=ApiError(4, "offline"))
    with pytest.raises(HomeAssistantError):
        await _set_setpoint(hass, 55)
    attributes = _event(hass)
    assert "system_id" not in attributes
    assert "value_id" not in attributes and "response" not in attributes
    for value in attributes.values():
        assert str(SYSTEM.id) not in str(value)
        assert str(SYSTEM.gateway_id) not in str(value)


async def test_raising_listener_does_not_fail_the_write(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A sent write stays ok and the other listeners still hear about it."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    writer = mock_config_entry.runtime_data.writer

    def broken(result: str, record: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    seen: list[str] = []
    notified: list[bool] = []
    writer.async_add_event_listener(broken)
    writer.async_add_event_listener(lambda result, record: seen.append(result))
    writer.async_add_listener(lambda: notified.append(True))

    await _set_setpoint(hass, 55)

    mock_client.write_value.assert_awaited_once()
    assert writer.history[-1]["result"] == "ok"
    assert seen == ["ok"]
    assert notified
    _assert_event(hass, "ok")
    assert "Write result listener failed" in caplog.text


@pytest.mark.parametrize("read_back", ["55", "50"])
async def test_check_result_fires_once(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    read_back: str,
) -> None:
    """One write, several later polls: ok, then confirmed or not_applied exactly once."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    seen: list[str] = []
    mock_config_entry.runtime_data.writer.async_add_event_listener(
        lambda result, record: seen.append(result)
    )
    await _set_setpoint(hass, 55)
    mock_client.get_values.side_effect = lambda system, bundle, ids, first=False: [
        Value(i, read_back if i == DHW_SETPOINT else "0", 1) for i in ids
    ]
    for _ in range(3):
        freezer.tick(timedelta(seconds=120))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert seen == ["ok", "confirmed" if read_back == "55" else "not_applied"]

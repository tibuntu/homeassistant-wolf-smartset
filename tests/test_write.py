"""Write pipeline (ADR-Writes-012): every safeguard has its own test."""

import asyncio
from datetime import timedelta
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.wolf_smartset.api import ApiError, SystemState, Value
from custom_components.wolf_smartset.const import CONF_DRY_RUN, CONF_MAX_WRITES_PER_HOUR, DOMAIN

DHW_SETPOINT = 35000900000  # "Warmwassersolltemperatur eingestellt", 25-65 °C, step 1, value 50
DHW_ONCE = 22004200000  # "1x Warmwasser", switch
PROGRAM = 36005100001  # "Programmwahl (Heizung)", select
BOILER = 27000600001  # "Kesseltemperatur", read-only sensor


def _entity_id(hass: HomeAssistant, domain: str, parameter_id: int) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"1234_{parameter_id}")
    assert entity_id
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _set_setpoint(hass: HomeAssistant, value: float) -> None:
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _entity_id(hass, "number", DHW_SETPOINT), "value": value},
        blocking=True,
    )


def _history(entry: MockConfigEntry) -> list[dict[str, Any]]:
    return entry.runtime_data.writer.history


async def test_dry_run_is_default_and_only_logs(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without options nothing is sent; an INFO line names parameter, old and new value."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    caplog.set_level(logging.INFO)

    await _set_setpoint(hass, 55)

    mock_client.write_value.assert_not_called()
    assert "Dry run: would write Warmwassersolltemperatur eingestellt" in caplog.text
    assert "50 -> 55" in caplog.text
    assert _history(mock_config_entry)[-1]["result"] == "dry_run"
    assert hass.states.get(_entity_id(hass, "number", DHW_SETPOINT)).state == "50.0"


async def test_no_op_sends_nothing(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Writing the current value is skipped, even with writes enabled (EEPROM)."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 50)
    mock_client.write_value.assert_not_called()
    assert _history(mock_config_entry)[-1]["result"] == "unchanged"


async def test_write_is_sent_shown_and_persisted(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    """Portal payload, optimistic state, history in .storage."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 55)

    mock_client.write_value.assert_awaited_once()
    _, bundle, value_id, value, name = mock_client.write_value.call_args.args
    assert (bundle, value_id, value, name) == (
        1000,
        DHW_SETPOINT,
        "55",
        "Warmwassersolltemperatur eingestellt",
    )
    assert hass.states.get(_entity_id(hass, "number", DHW_SETPOINT)).state == "55.0"
    record = _history(mock_config_entry)[-1]
    assert (record["old"], record["new"], record["result"]) == ("50", "55", "ok")
    await hass.async_block_till_done()
    stored = hass_storage[f"{DOMAIN}.{mock_config_entry.entry_id}.history"]["data"]["history"]
    assert stored[-1]["result"] == "ok"


async def test_switch_and_select_write_list_values(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The switch writes 1, the select writes the value behind the display text."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": _entity_id(hass, "switch", DHW_ONCE)}, blocking=True
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": _entity_id(hass, "select", PROGRAM), "option": "Standby"},
        blocking=True,
    )
    written = [(c.args[2], c.args[3]) for c in mock_client.write_value.call_args_list]
    assert written == [(DHW_ONCE, "1"), (PROGRAM, "0")]


async def test_validation_before_sending(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Step, range, read-only and unknown options are refused locally."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    with pytest.raises(ServiceValidationError, match="step"):
        await _set_setpoint(hass, 55.5)

    coordinator = mock_config_entry.runtime_data.coordinators[1234]
    writer = mock_config_entry.runtime_data.writer
    parameters = coordinator.description.parameters
    for parameter_id, value, key in (
        (DHW_SETPOINT, "70", "out_of_range"),
        (BOILER, "40", "not_writable"),
        (DHW_ONCE, "2", "invalid_option"),
    ):
        with pytest.raises(ServiceValidationError) as err:
            await writer.async_write(coordinator, parameters[parameter_id], value, source="test")
        assert err.value.translation_key == key
    mock_client.write_value.assert_not_called()


async def test_access_level_is_respected(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An account with read-only access cannot write."""
    mock_client.get_system_state.return_value = SystemState(True, 1)
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    with pytest.raises(ServiceValidationError) as err:
        await _set_setpoint(hass, 55)
    assert err.value.translation_key == "access_denied"
    mock_client.write_value.assert_not_called()


async def test_rate_limit(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The third write within an hour is blocked and recorded."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 2})
    await _set_setpoint(hass, 51)
    await _set_setpoint(hass, 52)
    with pytest.raises(HomeAssistantError) as err:
        await _set_setpoint(hass, 53)
    assert err.value.translation_key == "rate_limited"
    assert mock_client.write_value.await_count == 2
    assert _history(mock_config_entry)[-1]["result"] == "rate_limited"


async def test_one_write_at_a_time(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Concurrent writes are serialised by the lock."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    running = 0
    peak = 0

    async def slow_write(*args: Any) -> dict:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return {}

    mock_client.write_value = AsyncMock(side_effect=slow_write)
    await asyncio.gather(
        _set_setpoint(hass, 55),
        hass.services.async_call(
            "switch", "turn_on", {"entity_id": _entity_id(hass, "switch", DHW_ONCE)}, blocking=True
        ),
    )
    assert (mock_client.write_value.await_count, peak) == (2, 1)


async def test_write_error_is_reported_not_retried(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A failed write raises, keeps the old state and is recorded."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    mock_client.write_value = AsyncMock(side_effect=ApiError(4, "offline"))
    with pytest.raises(HomeAssistantError) as err:
        await _set_setpoint(hass, 55)
    assert err.value.translation_key == "write_failed"
    assert mock_client.write_value.await_count == 1
    assert hass.states.get(_entity_id(hass, "number", DHW_SETPOINT)).state == "50.0"
    assert _history(mock_config_entry)[-1]["result"] == "error"


@pytest.mark.parametrize(("read_back", "result"), [("55", "ok"), ("50", "not_applied")])
async def test_next_poll_confirms_or_corrects(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    read_back: str,
    result: str,
) -> None:
    """The poll after the write either confirms the value or restores the real one."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 55)

    mock_client.get_values.side_effect = lambda system, bundle, ids, first=False: [
        Value(i, read_back if i == DHW_SETPOINT else "0", 1) for i in ids
    ]
    freezer.tick(timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    record = _history(mock_config_entry)[-1]
    assert (record["result"], record["confirmed"], record["read_back"]) == (
        result,
        result == "ok",
        read_back,
    )
    assert hass.states.get(_entity_id(hass, "number", DHW_SETPOINT)).state == f"{read_back}.0"


async def test_early_poll_keeps_the_written_value(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A poll within 30 s (or in flight during the write) may still read the old value."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    await _set_setpoint(hass, 55)
    assert _history(mock_config_entry)[-1]["confirmed"] is None

    coordinator = mock_config_entry.runtime_data.coordinators[1234]
    await coordinator.async_refresh()  # the fake portal still returns 50

    assert hass.states.get(_entity_id(hass, "number", DHW_SETPOINT)).state == "55.0"
    assert _history(mock_config_entry)[-1]["confirmed"] is None
    await _set_setpoint(hass, 55)  # no-op: the written value is still the known one
    assert mock_client.write_value.await_count == 1


async def test_restart_marks_pending_writes_unconfirmed(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    """A confirmation lost by a restart is recorded as confirmed: false."""
    hass_storage[f"{DOMAIN}.{mock_config_entry.entry_id}.history"] = {
        "version": 1,
        "key": f"{DOMAIN}.{mock_config_entry.entry_id}.history",
        "data": {"history": [{"result": "ok", "confirmed": None, "old": "0", "new": "1"}]},
    }
    await _setup(hass, mock_config_entry)
    assert _history(mock_config_entry)[-1]["confirmed"] is False
    assert _history(mock_config_entry)[-1]["read_back"] is None


async def test_undo_restores_previous_value(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The undo button writes the old value back through the same pipeline."""
    await _setup(hass, mock_config_entry, **{CONF_DRY_RUN: False})
    button = er.async_get(hass).async_get_entity_id("button", DOMAIN, "1234_undo")
    assert button
    assert hass.states.get(button).state == "unavailable"

    await _set_setpoint(hass, 55)
    assert hass.states.get(button).state != "unavailable"
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)

    assert [c.args[3] for c in mock_client.write_value.call_args_list] == ["55", "50"]
    assert _history(mock_config_entry)[-2]["undone"] is True
    assert _history(mock_config_entry)[-1]["source"] == "undo"

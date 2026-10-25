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
from custom_components.wolf_smartset.model import parse_description
from custom_components.wolf_smartset.write import CONFIRM_AFTER_SECONDS, format_number, same_value

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
        (
            {"GatewayUsername": "WL123456", "Values": [{"ValueId": DHW_SETPOINT, "Name": "x"}]},
            {
                "GatewayUsername": "**REDACTED**",
                "Values": [{"ValueId": DHW_SETPOINT, "Name": "**REDACTED**"}],
            },
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

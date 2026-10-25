"""Setup, entities and polling (ADR-Polling-003)."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.wolf_smartset.api import AuthError, SystemState, TooManyRequests, Value
from custom_components.wolf_smartset.const import DOMAIN


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(hass: HomeAssistant, domain: str, parameter_id: int) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"1234_{parameter_id}")
    assert entity_id
    return entity_id


async def test_entities_and_devices(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """User-level parameters enabled, expert ones disabled; one device per submenu."""
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    registry = er.async_get(hass)
    dhw = registry.async_get(_entity_id(hass, "switch", 22004200000))
    sparfaktor = registry.async_get(_entity_id(hass, "number", 36000600001))
    assert dhw and not dhw.disabled
    assert sparfaktor and sparfaktor.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    assert hass.states.get(dhw.entity_id).state == "off"  # seeded from the description
    setpoint = hass.states.get(_entity_id(hass, "number", 35000900000))
    assert (setpoint.state, setpoint.attributes["min"], setpoint.attributes["max"]) == (
        "50.0",
        25.0,
        65.0,
    )
    assert hass.states.get(_entity_id(hass, "select", 36005100001)).state == "Auto"

    devices = {
        d.name
        for d in dr.async_entries_for_config_entry(dr.async_get(hass), mock_config_entry.entry_id)
    }
    assert devices == {"Home", "Heizgerät", "Bedienmodul BM-2 0", "Mischermodul MM1", "ISM"}


async def test_poll_only_enabled_parameters(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Expert bundles are not requested while their entities are disabled."""
    await _setup(hass, mock_config_entry)
    mock_client.get_values.reset_mock(side_effect=True)
    mock_client.get_values.return_value = [Value(22004200000, "1", 1)]
    freezer.tick(timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    bundles = {call.args[1] for call in mock_client.get_values.call_args_list}
    assert bundles == {1000}
    assert hass.states.get(_entity_id(hass, "switch", 22004200000)).state == "on"


async def test_offline_makes_entities_unavailable(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An offline gateway skips value requests."""
    await _setup(hass, mock_config_entry)
    mock_client.get_values.reset_mock()
    mock_client.get_system_state.return_value = SystemState(False, 4)
    freezer.tick(timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id(hass, "switch", 22004200000)).state == STATE_UNAVAILABLE
    mock_client.get_values.assert_not_called()


async def test_throttling_backs_off(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Throttling doubles the interval, raises a repair issue, success resets it."""
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinators[1234]
    mock_client.get_values.side_effect = TooManyRequests("x")
    for _ in range(3):
        freezer.tick(coordinator.update_interval)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert coordinator.update_interval == timedelta(seconds=960)
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, f"throttled_{mock_config_entry.entry_id}_1234"
    )

    mock_client.get_values.side_effect = None
    mock_client.get_values.return_value = [Value(22004200000, "0", 1)]
    freezer.tick(coordinator.update_interval)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.update_interval == timedelta(seconds=120)
    assert not ir.async_get(hass).async_get_issue(
        DOMAIN, f"throttled_{mock_config_entry.entry_id}_1234"
    )


async def test_auth_error_starts_reauth(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A rejected password during setup starts the reauth flow."""
    mock_client.get_description.side_effect = AuthError("x")
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_unload_closes_session(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Unload releases the portal session."""
    await _setup(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    mock_client.close.assert_awaited_once()


async def test_device_change_keeps_entity(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A new device assignment moves the entity; unique_id and entity_id stay."""
    mock_config_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    system = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id, identifiers={(DOMAIN, "1234")}
    )
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "1234_27004800001",
        config_entry=mock_config_entry,
        device_id=system.id,
        suggested_object_id="zuhause_verdichterfrequenz",
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    new = registry.async_get(old.entity_id)
    assert new is not None
    assert (new.id, new.unique_id, new.entity_id) == (old.id, old.unique_id, old.entity_id)
    heat_generator = dr.async_get_device_id_by_identifier(
        hass, (DOMAIN, "1234_heizgerat"), config_entry_id=mock_config_entry.entry_id
    )
    assert new.device_id == heat_generator != system.id

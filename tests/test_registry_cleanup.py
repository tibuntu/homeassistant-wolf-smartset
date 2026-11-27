"""Registry entries left behind when a parameter moved to another platform."""

import copy
from dataclasses import asdict
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import RELOAD_AFTER_UPDATE_DELAY, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.wolf_smartset.api import System
from custom_components.wolf_smartset.const import CONF_SYSTEMS, DOMAIN

from .conftest import SYSTEM

Disabler = er.RegistryEntryDisabler
SPARFAKTOR = "1234_36000600001"  # expert number until 0.6.0, sensor since
EXPERT_ENUM = "1234_27005200001"  # expert select until 0.6.0, sensor since
EXPERT_VALUE = "1234_27004400001"


def _seed(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    domain: str,
    unique_id: str,
    disabled_by: Disabler | None = None,
) -> er.RegistryEntry:
    return er.async_get(hass).async_get_or_create(
        domain, DOMAIN, unique_id, config_entry=entry, disabled_by=disabled_by
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _occurrences(obj: Any, parameter_id: int) -> list[tuple[list, dict]]:
    """(containing list, descriptor) for every occurrence of a parameter."""
    found: list[tuple[list, dict]] = []
    if isinstance(obj, dict):
        for value in obj.values():
            found += _occurrences(value, parameter_id)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and item.get("ParameterId") == parameter_id:
                found.append((obj, item))
            else:
                found += _occurrences(item, parameter_id)
    return found


def _get(hass: HomeAssistant, domain: str, unique_id: str) -> er.RegistryEntry | None:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    return registry.async_get(entity_id) if entity_id else None


async def test_enabled_stale_entry_enables_its_sibling(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Enabled stale number: gone, sensor enabled with the user's customisation.

    Enabling makes HA reload the entry once; the reload finds nothing left to do.
    """
    mock_config_entry.add_to_hass(hass)
    stale = _seed(hass, mock_config_entry, "number", SPARFAKTOR)
    er.async_get(hass).async_update_entity(
        stale.entity_id, name="Savings", icon="mdi:leaf", area_id="cellar"
    )
    _seed(hass, mock_config_entry, "sensor", SPARFAKTOR, Disabler.INTEGRATION)
    await _setup(hass, mock_config_entry)

    assert _get(hass, "number", SPARFAKTOR) is None
    sensor = _get(hass, "sensor", SPARFAKTOR)
    assert sensor
    assert sensor.disabled_by is None
    assert (sensor.name, sensor.icon, sensor.area_id) == ("Savings", "mdi:leaf", "cellar")

    loads = mock_client.get_description.call_count
    for _ in range(2):
        freezer.tick(timedelta(seconds=RELOAD_AFTER_UPDATE_DELAY + 1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert mock_client.get_description.call_count == loads + 1  # exactly one reload
    assert mock_config_entry.state is ConfigEntryState.LOADED
    state = hass.states.get(sensor.entity_id)
    assert state
    assert state.state != STATE_UNAVAILABLE


async def test_customisation_moves_where_the_sibling_has_none(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Labels, aliases and a user hide move; the sibling's own name wins."""
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    stale = _seed(hass, mock_config_entry, "number", SPARFAKTOR)
    registry.async_update_entity(
        stale.entity_id,
        name="Old",
        icon="mdi:leaf",
        labels={"heating"},
        aliases=["savings factor"],
        hidden_by=er.RegistryEntryHider.USER,
    )
    sibling = _seed(hass, mock_config_entry, "sensor", SPARFAKTOR, Disabler.INTEGRATION)
    registry.async_update_entity(sibling.entity_id, name="New")
    await _setup(hass, mock_config_entry)

    sensor = _get(hass, "sensor", SPARFAKTOR)
    assert sensor
    assert (sensor.name, sensor.icon, sensor.labels) == ("New", "mdi:leaf", {"heating"})
    assert sensor.aliases == ["savings factor"]
    assert sensor.hidden_by is er.RegistryEntryHider.USER


async def test_kind_flip_of_a_writable_parameter_keeps_its_entity(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    description: dict[str, Any],
) -> None:
    """A partial description (IsReadOnly missing) turns a number into a sensor.

    The number is a user-level parameter, so its entry stays with name and entity_id.
    """
    for _, item in _occurrences(description, 36002900001):
        item.pop("IsReadOnly", None)
    mock_config_entry.add_to_hass(hass)
    number = _seed(hass, mock_config_entry, "number", "1234_36002900001")
    er.async_get(hass).async_update_entity(number.entity_id, name="Correction")
    await _setup(hass, mock_config_entry)

    assert _get(hass, "sensor", "1234_36002900001")  # the flip happened
    kept = _get(hass, "number", "1234_36002900001")
    assert kept
    assert (kept.entity_id, kept.name) == (number.entity_id, "Correction")


async def test_each_entry_is_judged_by_its_own_system(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    description: dict[str, Any],
) -> None:
    """The second system lacks Sparfaktor, so its number stays."""
    cabin = System(4321, 8765, "Cabin", None)
    cabin_description = copy.deepcopy(description)
    for occurrences, item in _occurrences(cabin_description, 36000600001):
        occurrences.remove(item)
    mock_client.get_description.side_effect = lambda system: (
        cabin_description if system.id == cabin.id else description
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=mock_config_entry.unique_id,
        data={**mock_config_entry.data, CONF_SYSTEMS: [asdict(SYSTEM), asdict(cabin)]},
    )
    entry.add_to_hass(hass)
    for unique_id in (SPARFAKTOR, "4321_36000600001"):
        _seed(hass, entry, "number", unique_id)
        _seed(hass, entry, "sensor", unique_id, Disabler.INTEGRATION)
    await _setup(hass, entry)

    assert _get(hass, "number", SPARFAKTOR) is None
    assert _get(hass, "number", "4321_36000600001")


async def test_no_sibling_no_removal(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Without a sensor entry the stale number stays (safety check)."""
    mock_config_entry.add_to_hass(hass)
    _seed(hass, mock_config_entry, "number", SPARFAKTOR)
    with patch("custom_components.wolf_smartset.sensor.add_entities"):
        await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert _get(hass, "sensor", SPARFAKTOR) is None
    assert _get(hass, "number", SPARFAKTOR)


async def test_disabled_stale_entry_and_user_disabled_sibling(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Stale entries go; only siblings the integration disabled are ever enabled."""
    mock_config_entry.add_to_hass(hass)
    _seed(hass, mock_config_entry, "select", EXPERT_ENUM, Disabler.INTEGRATION)
    _seed(hass, mock_config_entry, "number", EXPERT_VALUE)
    _seed(hass, mock_config_entry, "sensor", EXPERT_VALUE, Disabler.USER)
    await _setup(hass, mock_config_entry)

    assert _get(hass, "select", EXPERT_ENUM) is None
    enum_sensor = _get(hass, "sensor", EXPERT_ENUM)
    assert enum_sensor
    assert enum_sensor.disabled_by is Disabler.INTEGRATION
    assert _get(hass, "number", EXPERT_VALUE) is None
    value_sensor = _get(hass, "sensor", EXPERT_VALUE)
    assert value_sensor
    assert value_sensor.disabled_by is Disabler.USER


async def test_entries_without_a_sibling_stay(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Missing, unmapped or foreign-system parameters and the own entities stay."""
    mock_config_entry.add_to_hass(hass)
    kept = [
        ("number", "1234_99999999999"),  # not in the description (portal hiccup)
        ("number", "1234_22003400000"),  # in the description, not mapped
        ("number", "9999_36000600001"),  # system not selected
        ("number", "1234_36000600001_x"),  # not a parameter unique ID
    ]
    for domain, unique_id in kept:
        _seed(hass, mock_config_entry, domain, unique_id)
    await _setup(hass, mock_config_entry)

    for domain, unique_id in kept:
        assert _get(hass, domain, unique_id), unique_id
    assert _get(hass, "button", "1234_undo")
    assert _get(hass, "binary_sensor", "1234_connectivity")
    assert _get(hass, "event", "1234_write")

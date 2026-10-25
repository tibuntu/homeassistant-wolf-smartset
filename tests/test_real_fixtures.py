"""The owner's installation, recorded with scripts/record_fixtures.py (redacted)."""

import json
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wolf_smartset.model import Kind, parse_description

from .conftest import DESCRIPTION, FIXTURES

REAL = FIXTURES / "real"


def _load(name: str):
    return json.loads((REAL / name).read_text(encoding="utf-8"))


def test_real_description_matches_example_model() -> None:
    """Same parameters, platforms, bundles and devices as the test fixture."""
    real = parse_description(_load("description_0.json")).parameters
    example = parse_description(DESCRIPTION).parameters

    def shape(p):
        return (p.kind, p.writable, p.bundle_id, p.device, p.label)

    assert {k: shape(p) for k, p in real.items()} == {k: shape(p) for k, p in example.items()}
    assert real[22004200000].kind is Kind.SWITCH


def test_access_level_and_online_flag() -> None:
    """GetSystemStateList carries AccessLevel next to GatewayState."""
    state = _load("system_state_0.json")[0]
    assert (state["GatewayState"]["IsOnline"], state["AccessLevel"]) == (True, 4)


def test_every_requested_user_value_is_returned() -> None:
    """All user-level values come back with State OK; one may lack a value."""
    values = _load("values_0.json")["Values"]
    real = parse_description(_load("description_0.json")).parameters
    requested = {p.value_id for p in real.values() if p.kind and p.bundle_id == 1000}
    assert {v["ValueId"] for v in values} == requested
    assert {v["State"] for v in values} == {1}


# Disabled by default on a new installation, apart from the expert (Fachmann) parameters.
DISABLED_BY_DEFAULT = {
    4000100001: "Ausgang MKP",  # schema port, duplicate of "Mischerkreispumpe" 4007000001
    27016200001: "Verbrauch aktueller Monat",
    27016400001: "Verbrauch aktuelles Jahr",
    27016600001: "Verbrauch Vorjahr",
    27016800001: "Verbrauch Vorvorjahr",
    27017100001: "MAZ aktueller Monat",
    27017200001: "JAZ aktuelles Jahr",
    27017300001: "JAZ Vorjahr",
    27017400001: "JAZ Vorvorjahr",
    27017500001: "Verbrauch Vortag",
    27017700001: "TAZ Vortag",
    36000000001: "Raumtemperatur",
}
EXPERT_PARAMETERS = 168


async def test_disabled_by_default_on_new_installation(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A first setup with the owner's description: which entities start disabled."""
    description = _load("description_0.json")
    mock_client.get_description.return_value = description
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    parameters = parse_description(description).parameters
    entries = {
        int(e.unique_id.removeprefix("1234_")): e
        for e in er.async_entries_for_config_entry(er.async_get(hass), mock_config_entry.entry_id)
        if e.unique_id != "1234_undo"
    }
    disabled = {
        pid for pid, e in entries.items() if e.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    }
    assert {pid: parameters[pid].label for pid in disabled if not parameters[pid].expert} == (
        DISABLED_BY_DEFAULT
    )
    assert sum(parameters[pid].expert for pid in disabled) == EXPERT_PARAMETERS
    assert all(e.disabled_by is None for pid, e in entries.items() if pid not in disabled)
    # The tab parameter stays enabled, its schema duplicate does not.
    assert entries[4007000001].disabled_by is None
    assert parameters[4000100001].duplicate_of == 4007000001

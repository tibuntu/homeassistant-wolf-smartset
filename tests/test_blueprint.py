"""The PV-surplus hot water blueprint is valid and fires once per surplus episode."""

from datetime import timedelta
from pathlib import Path
import shutil

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml
import pytest
from pytest_homeassistant.common import (
    async_fire_time_changed,
    async_mock_service,
)

RELATIVE = Path("blueprints/automation/wolf_smartset/dhw_charge_on_pv_surplus.yaml")
BLUEPRINT = Path(__file__).parent.parent / RELATIVE

SURPLUS = "sensor.pv_surplus"
DHW_TEMP = "sensor.dhw_temp"
SWITCH = "switch.wolf_one_time_dhw_charge"
INPUTS = {
    "surplus_sensor": SURPLUS,
    "surplus_threshold": 1500,
    "hold_time": {"minutes": 10},
    "dhw_temperature_sensor": DHW_TEMP,
    "dhw_temperature_limit": 45,
    "cooldown_minutes": 180,
    "dhw_switch": SWITCH,
}


def test_blueprint_schema() -> None:
    """The file passes Home Assistant's blueprint schema and declares what the README lists."""
    data = load_yaml(str(BLUEPRINT))
    BLUEPRINT_SCHEMA(data)
    blueprint = Blueprint(data, expected_domain="automation", schema=BLUEPRINT_SCHEMA)
    assert set(blueprint.inputs) == set(INPUTS)
    switch_selector = selector.validate_selector(
        data["blueprint"]["input"]["dhw_switch"]["selector"]
    )["entity"]
    assert switch_selector["integration"] == "wolf_smartset"
    assert switch_selector["domain"] == ["switch"]
    assert data["actions"][0]["action"] == "switch.turn_on"
    assert [c["condition"] for c in data["conditions"]] == ["numeric_state", "state", "template"]


def _surplus_episode(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    hass.states.async_set(SURPLUS, "0")
    hass.states.async_set(SURPLUS, "3000")
    freezer.tick(timedelta(minutes=10, seconds=1))
    async_fire_time_changed(hass)


@pytest.fixture
async def calls(hass: HomeAssistant, tmp_path: Path):
    """The blueprint instantiated as an automation; switch.turn_on is a recorded fake."""
    target = tmp_path / RELATIVE
    target.parent.mkdir(parents=True)
    shutil.copy(BLUEPRINT, target)
    hass.config.config_dir = str(tmp_path)
    hass.states.async_set(SURPLUS, "0")
    hass.states.async_set(DHW_TEMP, "40")
    hass.states.async_set(SWITCH, "off")
    recorded = async_mock_service(hass, "switch", "turn_on")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": "wolf_smartset/dhw_charge_on_pv_surplus.yaml",
                    "input": INPUTS,
                }
            }
        },
    )
    await hass.async_block_till_done()
    return recorded


async def test_once_per_episode_and_cooldown(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: list
) -> None:
    """One turn_on per episode; a second episode inside the cooldown does nothing."""
    # Not above the threshold long enough: nothing.
    hass.states.async_set(SURPLUS, "3000")
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not calls

    freezer.tick(timedelta(minutes=5, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["entity_id"] == [SWITCH]

    # Surplus stays high: no further write.
    freezer.tick(timedelta(minutes=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls) == 1

    # New episode inside the cooldown (the fake switch stays "off"): blocked.
    _surplus_episode(hass, freezer)
    await hass.async_block_till_done()
    assert len(calls) == 1

    # New episode after the cooldown: fires again.
    freezer.tick(timedelta(hours=3))
    _surplus_episode(hass, freezer)
    await hass.async_block_till_done()
    assert len(calls) == 2


@pytest.mark.parametrize(("temperature", "switch_state"), [("46", "off"), ("40", "on")])
async def test_conditions_block(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calls: list,
    temperature: str,
    switch_state: str,
) -> None:
    """A warm tank or a running charge suppresses the write."""
    hass.states.async_set(DHW_TEMP, temperature)
    hass.states.async_set(SWITCH, switch_state)
    _surplus_episode(hass, freezer)
    await hass.async_block_till_done()
    assert not calls

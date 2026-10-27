"""Stable translation keys for curated parameters (ADR-Model-016)."""

import json
import re
from typing import Any
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wolf_smartset.const import DOMAIN
from custom_components.wolf_smartset.model import PLATFORMS, Kind, Parameter, parse_description
from custom_components.wolf_smartset.translation_keys import TRANSLATION_KEYS

from .conftest import FIXTURES
from .test_model import _descriptors

COMPONENT = FIXTURES.parent.parent / "custom_components" / "wolf_smartset"
# hassfest: [a-z0-9-_]+, no leading or trailing hyphen or underscore
KEY_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-_]*[a-z0-9])?$")
CURATED = {
    (platform, key) for platform, table in TRANSLATION_KEYS.items() for key in table.values()
}


def _entity_translations(name: str) -> dict[str, dict[str, dict[str, str]]]:
    data = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
    return data["entity"]


def test_every_key_matches_a_fixture_parameter_on_its_platform(description: dict[str, Any]) -> None:
    """Each row names an existing parameter of the curated platform; all others have no key."""
    parameters = parse_description(description).parameters
    for platform, table in TRANSLATION_KEYS.items():
        for parameter_id, key in table.items():
            parameter = parameters[parameter_id]
            assert parameter.kind and PLATFORMS[parameter.kind] == platform, key
            assert parameter.translation_key == key
    keyed = {pid for table in TRANSLATION_KEYS.values() for pid in table}
    for parameter in parameters.values():
        if parameter.parameter_id not in keyed:
            assert parameter.translation_key is None, parameter.label


def test_unknown_parameter_has_no_key() -> None:
    """A parameter outside the table keeps the Wolf label."""
    parameter = Parameter(
        parameter_id=1,
        value_id=1,
        name="Irgendwas",
        prefix=None,
        group=None,
        unit="°C",
        minimum=None,
        maximum=None,
        step=None,
        decimals=None,
        options={},
        selectable=[],
        value=None,
        control_type=6,
        bundle_id=1000,
        writable=False,
        expert=False,
    )
    assert parameter.kind is Kind.SENSOR
    assert parameter.translation_key is None


def test_key_only_on_the_curated_platform(description: dict[str, Any]) -> None:
    """A read-only '1x Warmwasser' is an enum sensor; the switch key does not apply."""
    for descriptor in _descriptors(description, 22004200000):
        descriptor["IsReadOnly"] = True
    parameter = parse_description(description).parameters[22004200000]
    assert parameter.kind is Kind.ENUM
    assert parameter.translation_key is None


def test_time_program_selectors_have_keys(description: dict[str, Any]) -> None:
    """The weekly program selectors are curated like 'Programmwahl'."""
    parameters = parse_description(description).parameters
    assert parameters[36001600001].translation_key == "time_program_heating"
    assert parameters[35000400000].translation_key == "time_program_dhw"


def test_keys_are_unique_per_platform_and_valid() -> None:
    """Dashboards look keys up per platform; hassfest restricts the characters."""
    for platform, table in TRANSLATION_KEYS.items():
        keys = list(table.values())
        assert len(set(keys)) == len(keys), platform
        assert all(KEY_PATTERN.match(key) for key in keys), platform
    assert set(TRANSLATION_KEYS) <= set(PLATFORMS.values())


def test_translations_name_every_key_and_nothing_else(description: dict[str, Any]) -> None:
    """strings.json, en and de name exactly the curated keys; German names are the Wolf labels."""
    strings = _entity_translations("strings.json")
    assert strings == _entity_translations("translations/en.json")
    de = _entity_translations("translations/de.json")
    parameters = parse_description(description).parameters
    for translations in (strings, de):
        named = {
            (platform, key)
            for platform, keys in translations.items()
            for key in keys
            if (platform, key) != ("button", "undo")
        }
        assert named == CURATED
        for platform, keys in translations.items():
            for key, entry in keys.items():
                assert set(entry) == {"name"}, (platform, key)
                assert entry["name"] == entry["name"].strip(), (platform, key)
    for platform, table in TRANSLATION_KEYS.items():
        for parameter_id, key in table.items():
            assert de[platform][key]["name"] == parameters[parameter_id].label


async def test_registry_keeps_entity_ids_and_gets_translation_keys(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Existing entity IDs survive; curated entities are named by translation, others by label."""
    registry = er.async_get(hass)
    mock_config_entry.add_to_hass(hass)
    # An entity created by an earlier release under its German name.
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "1234_27000500001",
        suggested_object_id="heizgerat_aussentemperatur",
        config_entry=mock_config_entry,
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    outside = registry.async_get(old.entity_id)
    assert outside and outside.entity_id == "sensor.heizgerat_aussentemperatur"
    assert outside.translation_key == "outside_temperature"
    assert outside.original_name == "Outside temperature"  # test language is en
    assert hass.states.get(old.entity_id).attributes["friendly_name"] == (
        "Heizgerät Outside temperature"
    )

    entries = er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
    unique_ids = {e.unique_id for e in entries}
    mapped = [
        p
        for p in parse_description(mock_client.get_description.return_value).parameters.values()
        if p.kind
    ]
    assert unique_ids == {f"1234_{p.parameter_id}" for p in mapped} | {
        "1234_undo",
        "1234_connectivity",
    }
    keyed = {e.unique_id for e in entries if e.translation_key and e.unique_id != "1234_undo"}
    assert keyed == {f"1234_{p.parameter_id}" for p in mapped if p.translation_key}

    exhaust = registry.async_get_entity_id("sensor", DOMAIN, "1234_27004300001")
    assert exhaust
    entry = registry.async_get(exhaust)
    assert entry and entry.translation_key is None and entry.original_name == "Ablufttemperatur"

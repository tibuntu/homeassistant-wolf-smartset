"""Diagnostics do not leak credentials or identifiers."""

import json
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.wolf_smartset.const import CONF_DRY_RUN, DOMAIN


async def test_redaction(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Username, password, system and gateway IDs are redacted."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, mock_config_entry)
    text = json.dumps(result)
    for secret in ("user@example.com", "secret", "5678", '"Home"'):
        assert secret not in text
    assert result["systems"][0]["kinds"]["switch"] == 1
    assert result["writes"] == {"dry_run": True, "max_writes_per_hour": 20, "history": []}


async def test_write_response_in_diagnostics_is_redacted(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The last 50 history records, response included, show no identifiers."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_DRY_RUN: False})
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    mock_client.write_value.return_value = {
        "Values": [{"ValueId": 35000900000, "State": 1}],
        "SystemId": 1234,
        "GatewayId": 5678,
    }
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, "1234_35000900000")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 55}, blocking=True
    )

    result = await get_diagnostics_for_config_entry(hass, hass_client, mock_config_entry)
    record = result["writes"]["history"][-1]
    assert "system_id" not in record
    assert record["response"] == {
        "Values": [{"ValueId": 35000900000, "State": 1}],
        "SystemId": "**REDACTED**",
        "GatewayId": "**REDACTED**",
    }

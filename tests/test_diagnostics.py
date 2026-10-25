"""Diagnostics do not leak credentials or identifiers."""

import json
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


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

"""Config flow, reauth, reconfigure and options."""

from dataclasses import asdict
from typing import Any
from unittest.mock import MagicMock

from homeassistant import data_entry_flow
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wolf_smartset.api import (
    AuthError,
    CannotConnect,
    LoginFailed,
    PortalUnavailable,
    System,
)
from custom_components.wolf_smartset.const import (
    CONF_DRY_RUN,
    CONF_MAX_WRITES_PER_HOUR,
    CONF_SCAN_INTERVAL,
    CONF_SYSTEMS,
    DOMAIN,
)

from .conftest import SYSTEM

USER_INPUT = {CONF_USERNAME: "User@Example.com", CONF_PASSWORD: "secret"}


async def test_single_system(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """One system: the entry is created right away."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "user@example.com"
    assert result["data"][CONF_SYSTEMS] == [
        {"id": 1234, "gateway_id": 5678, "name": "Home", "share_id": None}
    ]


async def test_system_selection(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Several systems: the user picks a subset."""
    mock_client.get_systems.return_value = [SYSTEM, System(99, 98, "Cabin", 7)]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["step_id"] == "systems"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SYSTEMS: ["99"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert [s["id"] for s in result["data"][CONF_SYSTEMS]] == [99]


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (AuthError("x"), "invalid_auth"),
        (PortalUnavailable("x"), "portal_unavailable"),
        (LoginFailed("x"), "portal_unavailable"),
    ],
)
async def test_errors_recover(
    hass: HomeAssistant, mock_client: MagicMock, error: Exception, key: str
) -> None:
    """Errors are shown and the user can retry."""
    mock_client.get_systems.side_effect = error
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": key}
    mock_client.get_systems.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_password_too_long(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """The portal truncates passwords longer than 30 characters."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "u", CONF_PASSWORD: "x" * 31}
    )
    assert result["errors"] == {CONF_PASSWORD: "password_too_long"}
    mock_client.get_systems.assert_not_called()


async def test_already_configured(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """One entry per account."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["reason"] == "already_configured"


async def test_reconfigure_drops_a_system(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Deselecting a system removes its devices; the kept system keeps its entity IDs."""
    cabin = System(99, 98, "Cabin", 7)
    mock_client.get_systems.return_value = [SYSTEM, cabin]
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_SYSTEMS: [asdict(SYSTEM), asdict(cabin)]},
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id)
    kept = {e.unique_id: e.entity_id for e in entries if e.unique_id.startswith("1234_")}
    assert kept
    assert any(e.unique_id.startswith("99_") for e in entries)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "systems"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SYSTEMS: ["1234"]}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert [s["id"] for s in mock_config_entry.data[CONF_SYSTEMS]] == [1234]
    entries = er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id)
    assert {e.unique_id: e.entity_id for e in entries} == kept
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), mock_config_entry.entry_id)
    assert devices
    assert all(i.startswith("1234") for d in devices for _, i in d.identifiers)


async def test_reconfigure_error_recovers(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A failed listing shows an error; submitting retries."""
    mock_config_entry.add_to_hass(hass)
    mock_client.get_systems.side_effect = PortalUnavailable("x")
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "portal_unavailable"}
    mock_client.get_systems.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "systems"


async def test_reauth(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A new password is verified and stored."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new"}
    )
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new"


async def test_options(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Poll interval option."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 300, CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 5},
    )
    assert mock_config_entry.options == {
        CONF_SCAN_INTERVAL: 300,
        CONF_DRY_RUN: False,
        CONF_MAX_WRITES_PER_HOUR: 5,
    }


async def test_other_wolf_error_is_cannot_connect(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A WolfError without a dedicated message shows 'cannot_connect'."""
    mock_client.get_systems.side_effect = CannotConnect("x")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_with_wrong_password_shows_error(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A rejected new password keeps the reauth form open with an error."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    mock_client.get_systems.side_effect = AuthError("x")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert mock_config_entry.data[CONF_PASSWORD] == "secret"


async def test_unexpected_error(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Anything that is not a WolfError shows 'unknown' and is logged."""
    mock_client.get_systems.side_effect = RuntimeError("boom")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_no_systems(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """An account without systems cannot be added."""
    mock_client.get_systems.return_value = []
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_systems"


async def test_no_system_selected(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """An empty selection shows the systems step again with an error."""
    mock_client.get_systems.return_value = [SYSTEM, System(99, 98, "Cabin", 7)]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SYSTEMS: []})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "systems"
    assert result["errors"] == {"base": "no_system_selected"}


@pytest.mark.parametrize(
    "user_input",
    [
        {CONF_SCAN_INTERVAL: 10, CONF_DRY_RUN: True, CONF_MAX_WRITES_PER_HOUR: 5},
        {CONF_SCAN_INTERVAL: 120, CONF_DRY_RUN: True, CONF_MAX_WRITES_PER_HOUR: 0},
        {CONF_SCAN_INTERVAL: 120, CONF_DRY_RUN: True, CONF_MAX_WRITES_PER_HOUR: 61},
    ],
)
async def test_options_are_validated(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    user_input: dict[str, Any],
) -> None:
    """NumberSelector refuses values outside min and max server-side (review finding 10)."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    with pytest.raises(data_entry_flow.InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], user_input)


async def test_options_accept_floats(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The number selector delivers floats; they are stored as integers; the form serializes."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    fields = probatio.to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)
    assert len(fields) == 3
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 120.0, CONF_DRY_RUN: False, CONF_MAX_WRITES_PER_HOUR: 5.0},
    )
    assert mock_config_entry.options == {
        CONF_SCAN_INTERVAL: 120,
        CONF_DRY_RUN: False,
        CONF_MAX_WRITES_PER_HOUR: 5,
    }

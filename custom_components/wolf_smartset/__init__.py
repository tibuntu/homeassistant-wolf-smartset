"""Wolf SmartSet (read/write) integration."""

from functools import partial

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from .api import System, WolfClient
from .const import CONF_SYSTEMS, DOMAIN
from .coordinator import (
    WolfConfigEntry,
    WolfRuntimeData,
    WolfSystemCoordinator,
    create_http_client,
)
from .entity import system_device_info
from .write import WriteManager

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: WolfConfigEntry) -> bool:
    """One login for the account, one coordinator per selected system."""
    http = create_http_client()
    client = WolfClient(http, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinators: dict[int, WolfSystemCoordinator] = {}
    try:
        for stored in entry.data[CONF_SYSTEMS]:
            coordinator = WolfSystemCoordinator(hass, entry, client, System(**stored))
            await coordinator.async_config_entry_first_refresh()
            coordinators[coordinator.system.id] = coordinator
    except Exception:
        await client.close()
        await http.aclose()
        raise

    device_registry = dr.async_get(hass)
    for coordinator in coordinators.values():
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id, **system_device_info(coordinator)
        )
    _check_wolflink(hass, entry.data[CONF_USERNAME])

    writer = WriteManager(hass, entry)
    await writer.async_load()
    for coordinator in coordinators.values():
        # After each poll: confirm written values or correct them (ADR-Writes-012).
        entry.async_on_unload(
            coordinator.async_add_listener(partial(writer.async_check_pending, coordinator))
        )
    entry.runtime_data = WolfRuntimeData(http, client, coordinators, writer)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # The first refresh ran before any entity was listening; poll the enabled
    # parameters now instead of waiting a full interval with unknown states.
    for coordinator in coordinators.values():
        await coordinator.async_refresh()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WolfConfigEntry) -> bool:
    """Release the portal session and the HTTP client."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
        await entry.runtime_data.http.aclose()
    return unloaded


def _check_wolflink(hass: HomeAssistant, username: str) -> None:
    """Warn when core wolflink logs in with the same account (ADR-Integration-000)."""
    same_account = any(
        e.state is ConfigEntryState.LOADED
        and str(e.data.get(CONF_USERNAME, "")).lower() == username.lower()
        for e in hass.config_entries.async_entries("wolflink")
    )
    if same_account:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "wolflink_active",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="wolflink_active",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, "wolflink_active")

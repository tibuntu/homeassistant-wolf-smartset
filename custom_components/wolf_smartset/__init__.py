"""Wolf SmartSet (read/write) integration."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.httpx_client import create_async_httpx_client

from .api import System, WolfClient
from .const import CONF_SYSTEMS, DOMAIN
from .coordinator import WolfConfigEntry, WolfRuntimeData, WolfSystemCoordinator
from .entity import system_device_info

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: WolfConfigEntry) -> bool:
    """One login for the account, one coordinator per selected system."""
    http = create_async_httpx_client(hass, auto_cleanup=False)
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
    _check_wolflink(hass)

    entry.runtime_data = WolfRuntimeData(http, client, coordinators)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WolfConfigEntry) -> bool:
    """Release the portal session and the HTTP client."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
        await entry.runtime_data.http.aclose()
    return unloaded


def _check_wolflink(hass: HomeAssistant) -> None:
    """Warn when core wolflink also logs in from this IP (ADR-Integration-000)."""
    if any(
        e.state is ConfigEntryState.LOADED for e in hass.config_entries.async_entries("wolflink")
    ):
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

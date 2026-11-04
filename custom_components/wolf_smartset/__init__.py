"""Wolf SmartSet (read/write) integration."""

from functools import partial

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from .api import System, WolfClient
from .const import CONF_SYSTEMS, DOMAIN
from .coordinator import (
    WolfConfigEntry,
    WolfRuntimeData,
    WolfSystemCoordinator,
    async_login_backoff_hook,
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
    username = entry.data[CONF_USERNAME]
    client = WolfClient(
        http,
        username,
        entry.data[CONF_PASSWORD],
        on_login_backoff=await async_login_backoff_hook(hass, username),
    )
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
    # Systems dropped by the reconfigure flow: remove their devices (and with them
    # their entities). Identifiers are "<system id>" or "<system id>_<device>".
    selected = {str(i) for i in coordinators}
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if not any(i.split("_")[0] in selected for d, i in device.identifiers if d == DOMAIN):
            device_registry.async_remove_device(device.id)
    _check_wolflink(hass)

    writer = WriteManager(hass, entry)
    await writer.async_load()
    for coordinator in coordinators.values():
        # After each poll: confirm written values or correct them (ADR-Writes-012).
        entry.async_on_unload(
            coordinator.async_add_listener(partial(writer.async_check_pending, coordinator))
        )

    async def _close_session(_: Event) -> None:
        await client.close()

    # HA stop does not unload entries. A session left open keeps the gateway's push
    # bundles, and the next start reads frozen values for ~70 min until it expires.
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _close_session))
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


def _check_wolflink(hass: HomeAssistant) -> None:
    """Warn while core wolflink is loaded (ADR-Integration-000).

    Only the entry state is used; another integration's stored data is not ours to read.
    """
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

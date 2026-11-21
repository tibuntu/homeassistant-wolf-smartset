"""Write-result event: every write attempt in the logbook and as an automation trigger."""

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WolfConfigEntry, WolfSystemCoordinator
from .entity import system_device_info
from .write import EVENT_TYPES, WriteManager

PARALLEL_UPDATES = 0
# The system ID stays out, as in the diagnostics.
ATTRIBUTES = ("label", "parameter_id", "old", "new", "source", "error")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One write-result event per system, on the system device."""
    writer = entry.runtime_data.writer
    async_add_entities(
        WolfWriteEvent(writer, coordinator)
        for coordinator in entry.runtime_data.coordinators.values()
    )


class WolfWriteEvent(EventEntity):
    """Fires the result of each write to this system; no-ops fire nothing."""

    _attr_has_entity_name = True
    _attr_translation_key = "write"
    _attr_should_poll = False

    def __init__(self, writer: WriteManager, coordinator: WolfSystemCoordinator) -> None:
        """Attach to the system device."""
        self._attr_event_types = list(EVENT_TYPES)
        self._writer = writer
        self._system_id = coordinator.system.id
        self._attr_unique_id = f"{self._system_id}_write"
        self._attr_device_info = system_device_info(coordinator)

    async def async_added_to_hass(self) -> None:
        """Restore the last event and follow the write pipeline."""
        await super().async_added_to_hass()
        self.async_on_remove(self._writer.async_add_event_listener(self._handle_result))

    @callback
    def _handle_result(self, result: str, record: dict[str, Any]) -> None:
        if record["system_id"] != self._system_id:
            return
        self._trigger_event(result, {k: record[k] for k in ATTRIBUTES if k in record})
        self.async_write_ha_state()

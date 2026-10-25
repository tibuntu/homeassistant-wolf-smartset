"""Undo button for the latest change (ADR-Writes-012)."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WolfConfigEntry
from .entity import system_device_info

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One undo button per account, on the first system's device."""
    async_add_entities([WolfUndoButton(entry)])


class WolfUndoButton(ButtonEntity):
    """Writes the previous value of the latest applied change back."""

    _attr_has_entity_name = True
    _attr_translation_key = "undo"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(self, entry: WolfConfigEntry) -> None:
        """Attach to the first system's device."""
        self._entry = entry
        first = next(iter(entry.runtime_data.coordinators.values()))
        self._attr_unique_id = f"{first.system.id}_undo"
        self._attr_device_info = system_device_info(first)

    async def async_added_to_hass(self) -> None:
        """Follow history changes for availability."""
        self.async_on_remove(
            self._entry.runtime_data.writer.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Only pressable when there is something to undo."""
        return self._entry.runtime_data.writer.last_undoable() is not None

    async def async_press(self) -> None:
        """Undo through the normal write pipeline."""
        runtime = self._entry.runtime_data
        await runtime.writer.async_undo(runtime.coordinators)

"""Checkbox parameters (ControlType 5) as binary sensors."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WolfConfigEntry
from .entity import WolfEntity, add_entities
from .model import Kind

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    add_entities(entry, async_add_entities, (Kind.BINARY,), WolfBinarySensor)


class WolfBinarySensor(WolfEntity, BinarySensorEntity):
    """A checkbox parameter; the portal reports 'True' / 'False'."""

    @property
    def is_on(self) -> bool | None:
        """Map the portal's string to a boolean."""
        raw = self.raw_value
        return None if raw is None else raw.lower() in ("true", "1")

"""Checkbox parameters (ControlType 5) and the gateway connectivity as binary sensors."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import WolfConfigEntry, WolfSystemCoordinator
from .entity import WolfEntity, add_entities, system_device_info
from .model import Kind

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    add_entities(entry, async_add_entities, (Kind.BINARY,), WolfBinarySensor)
    async_add_entities(
        WolfConnectivitySensor(coordinator)
        for coordinator in entry.runtime_data.coordinators.values()
    )


class WolfConnectivitySensor(CoordinatorEntity[WolfSystemCoordinator], BinarySensorEntity):
    """Gateway online flag; tells an offline gateway apart from an unreachable portal."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WolfSystemCoordinator) -> None:
        """One per system, on the system device; named by its device class."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.system.id}_connectivity"
        self._attr_device_info = system_device_info(coordinator)

    @property
    def available(self) -> bool:
        """Stays available while the gateway is offline, unknown while the portal fails."""
        return self.coordinator.online is not None

    @property
    def is_on(self) -> bool | None:
        """Online flag of the last system state."""
        return self.coordinator.online


class WolfBinarySensor(WolfEntity, BinarySensorEntity):
    """A checkbox parameter; the portal reports 'True' / 'False'."""

    @property
    def is_on(self) -> bool | None:
        """Map the portal's string to a boolean."""
        raw = self.raw_value
        return None if raw is None else raw.lower() in ("true", "1")

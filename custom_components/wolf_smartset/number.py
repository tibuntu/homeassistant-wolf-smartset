"""Writable numeric parameters (ControlType 6)."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WolfConfigEntry, WolfSystemCoordinator
from .entity import WolfEntity, add_entities, parse_number
from .model import Kind, Parameter

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""
    add_entities(entry, async_add_entities, (Kind.NUMBER,), WolfNumber)


class WolfNumber(WolfEntity, NumberEntity):
    """A numeric setting with limits from the description."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: WolfSystemCoordinator, parameter: Parameter) -> None:
        """Limits are guaranteed by Parameter.kind."""
        super().__init__(coordinator, parameter)
        if parameter.minimum is None or parameter.maximum is None:
            raise ValueError(f"Parameter {parameter.parameter_id} has no limits")
        self._attr_native_min_value = parameter.minimum
        self._attr_native_max_value = parameter.maximum
        self._attr_native_step = parameter.step or 1.0
        if parameter.unit == "°C":
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_native_unit_of_measurement = parameter.unit

    @property
    def native_value(self) -> float | None:
        """Current setting."""
        return parse_number(self.raw_value)

    async def async_set_native_value(self, value: float) -> None:
        """Writing arrives in Phase 3."""
        self._raise_read_only()

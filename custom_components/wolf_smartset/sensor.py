"""Read-only parameters and the fault code as sensors."""

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import WolfConfigEntry, WolfFaultCoordinator, WolfSystemCoordinator
from .entity import WolfEntity, add_entities, current_faults, parse_number, system_device_info
from .model import CT_NUMERIC, Kind, Parameter

PARALLEL_UPDATES = 0

M = SensorStateClass.MEASUREMENT
T = SensorStateClass.TOTAL_INCREASING
D = SensorDeviceClass

# Wolf unit -> (device class, HA unit, state class)
UNITS: dict[str, tuple[SensorDeviceClass | None, str, SensorStateClass | None]] = {
    "°C": (D.TEMPERATURE, UnitOfTemperature.CELSIUS, M),
    "bar": (D.PRESSURE, UnitOfPressure.BAR, M),
    "Pa": (D.PRESSURE, UnitOfPressure.PA, M),
    "%": (None, PERCENTAGE, M),
    "kW": (D.POWER, UnitOfPower.KILO_WATT, M),
    "kWh": (D.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, T),
    "Wh;kWh": (D.ENERGY, UnitOfEnergy.WATT_HOUR, T),
    "Wh;kWh;MWh": (D.ENERGY, UnitOfEnergy.WATT_HOUR, T),
    "Std": (D.DURATION, UnitOfTime.HOURS, T),
    "min": (D.DURATION, UnitOfTime.MINUTES, None),
    "s": (D.DURATION, UnitOfTime.SECONDS, None),
    "sec": (D.DURATION, UnitOfTime.SECONDS, None),
    "l/min": (D.VOLUME_FLOW_RATE, UnitOfVolumeFlowRate.LITERS_PER_MINUTE, M),
    "m³/h": (D.VOLUME_FLOW_RATE, UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR, M),
    "Hz": (D.FREQUENCY, UnitOfFrequency.HERTZ, M),
    "U/min": (None, REVOLUTIONS_PER_MINUTE, M),
    "V": (D.VOLTAGE, UnitOfElectricPotential.VOLT, M),
}


def unit_mapping(
    parameter: Parameter,
) -> tuple[SensorDeviceClass | None, str, SensorStateClass | None]:
    """Device class, HA unit and state class for a parameter with a Wolf unit."""
    wolf_unit = parameter.unit or ""
    device_class, unit, state_class = UNITS.get(wolf_unit, (None, wolf_unit, None))
    # Closed periods (Vortag, Vorjahr, ...) may drop; total_increasing would read
    # every drop as a meter reset (ADR-Model-011).
    return device_class, unit, None if parameter.snapshot else state_class


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for read-only, enum and text parameters."""
    add_entities(entry, async_add_entities, (Kind.SENSOR, Kind.ENUM, Kind.TEXT), WolfSensor)
    async_add_entities(WolfFaultCodeSensor(faults) for faults in entry.runtime_data.faults.values())


class WolfFaultCodeSensor(CoordinatorEntity[WolfFaultCoordinator], SensorEntity):
    """ErrorCode of the first (assumed newest) current fault, plus the newest history entry.

    Faults last 1 to 3 minutes, shorter than the 10-minute read; the last_fault_*
    attributes keep a fault that came and went between two reads. Wolf's texts stay
    as sent; no Device, SystemName or IDs (rule 2).
    """

    _attr_has_entity_name = True
    _attr_translation_key = "fault_code"

    def __init__(self, coordinator: WolfFaultCoordinator) -> None:
        """One per system, on the system device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.values.system.id}_fault_code"
        self._attr_device_info = system_device_info(coordinator.values)

    @property
    def native_value(self) -> int | None:
        """ErrorCode of the first entry in CurrentMessages, None without one."""
        current = current_faults(self.coordinator.data)
        return current[0].get("ErrorCode") if current else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Current fault text and time, and the newest history entry."""
        current = current_faults(self.coordinator.data)
        now = current[0] if current else {}
        history = (self.coordinator.data or {}).get("HistoryMessages") or []
        last = history[0] if history else {}  # Index 0 = newest (recorded 2026-11-21)
        return {
            "description": now.get("Description"),
            "occurred": now.get("OccurTimeLocal"),
            "last_fault_code": last.get("ErrorCode"),
            "last_fault_description": last.get("Description"),
            "last_fault_occurred": last.get("OccurTimeLocal"),
            "last_fault_ended": last.get("OutgoingTimeLocal"),
        }


class WolfSensor(WolfEntity, SensorEntity):
    """A read-only parameter."""

    def __init__(self, coordinator: WolfSystemCoordinator, parameter: Parameter) -> None:
        """Device class and unit from the Wolf unit; enums from the list items."""
        super().__init__(coordinator, parameter)
        self._numeric = parameter.unit is not None or parameter.control_type == CT_NUMERIC
        if parameter.kind is Kind.ENUM:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(dict.fromkeys(parameter.options.values()))
            self._numeric = False
        elif parameter.kind is Kind.TEXT:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
            self._numeric = False
        elif parameter.unit is not None:
            (
                self._attr_device_class,
                self._attr_native_unit_of_measurement,
                self._attr_state_class,
            ) = unit_mapping(parameter)
        if self._numeric and parameter.decimals is not None:
            self._attr_suggested_display_precision = parameter.decimals

    @property
    def native_value(self) -> str | float | None:
        """Number, option text or raw string depending on the parameter."""
        raw = self.raw_value
        if raw is None:
            return None
        if self.parameter.kind is Kind.ENUM:
            return self.parameter.options.get(raw)
        return parse_number(raw) if self._numeric else raw

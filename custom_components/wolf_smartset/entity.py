"""Base entity for Wolf SmartSet parameters."""

from collections.abc import Iterable

from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import WolfConfigEntry, WolfSystemCoordinator
from .model import Kind, Parameter

_EMPTY = {"", "-", "--", "---", "----"}


def system_device_info(coordinator: WolfSystemCoordinator) -> DeviceInfo:
    """Device for the SmartSet system itself (gateway level)."""
    return DeviceInfo(
        identifiers={(DOMAIN, str(coordinator.system.id))},
        name=coordinator.system.name,
        manufacturer=MANUFACTURER,
        model="SmartSet system",
        configuration_url="https://www.wolf-smartset.com/",
    )


def parse_number(raw: str | None) -> float | None:
    """Portal values are strings; placeholders like '--' mean unknown."""
    if raw is None or raw.strip() in _EMPTY:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


class WolfEntity(CoordinatorEntity[WolfSystemCoordinator]):
    """One parameter; its ParameterId is the coordinator context (ADR-Polling-003)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WolfSystemCoordinator, parameter: Parameter) -> None:
        """Name, IDs and device from the parameter model."""
        super().__init__(coordinator, context=parameter.parameter_id)
        self.parameter = parameter
        system_id = coordinator.system.id
        self._attr_unique_id = f"{system_id}_{parameter.parameter_id}"
        self._attr_name = parameter.label
        self._attr_entity_registry_enabled_default = parameter.enabled_by_default
        if parameter.writable and parameter.kind in (Kind.NUMBER, Kind.SELECT):
            self._attr_entity_category = EntityCategory.CONFIG
        if parameter.device:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{system_id}_{parameter.device}")},
                name=coordinator.description.devices[parameter.device],
                manufacturer=MANUFACTURER,
                via_device_id=dr.async_get_device_id_by_identifier(
                    coordinator.hass,
                    (DOMAIN, str(system_id)),
                    config_entry_id=coordinator.config_entry.entry_id,
                ),
            )
        else:
            self._attr_device_info = system_device_info(coordinator)

    @property
    def raw_value(self) -> str | None:
        """Last raw value string, None when unknown."""
        raw = (self.coordinator.data or {}).get(self.parameter.value_id)
        return None if raw is None or raw.strip() in _EMPTY else raw

    def _raise_read_only(self) -> None:
        # ponytail: Phase 2 is read-only; the write pipeline (ADR-Writes-004/005) comes in Phase 3
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="writes_not_available"
        )


def add_entities(
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    kinds: Iterable[Kind],
    factory: type[WolfEntity],
) -> None:
    """Create one entity per parameter of the given kinds, for every system."""
    wanted = set(kinds)
    async_add_entities(
        factory(coordinator, parameter)
        for coordinator in entry.runtime_data.coordinators.values()
        for parameter in coordinator.description.parameters.values()
        if parameter.kind in wanted
    )

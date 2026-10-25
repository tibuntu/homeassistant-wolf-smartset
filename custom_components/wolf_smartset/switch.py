"""Known one-time actions, e.g. '1x Warmwasser' (ADR-Model-002)."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WolfConfigEntry, WolfSystemCoordinator
from .entity import WolfEntity, add_entities
from .model import KNOWN_SWITCHES, Kind, Parameter

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches for known one-time actions."""
    add_entities(entry, async_add_entities, (Kind.SWITCH,), WolfSwitch)


class WolfSwitch(WolfEntity, SwitchEntity):
    """On starts the action, off cancels it; the controller resets it itself."""

    def __init__(self, coordinator: WolfSystemCoordinator, parameter: Parameter) -> None:
        """Translated name instead of the German API name."""
        super().__init__(coordinator, parameter)
        self._attr_translation_key = KNOWN_SWITCHES[parameter.parameter_id]
        del self._attr_name  # without _attr_name, HA takes the name from translation_key

    @property
    def is_on(self) -> bool | None:
        """'1' means the action is running."""
        raw = self.raw_value
        return None if raw is None else raw == "1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Writing arrives in Phase 3."""
        self._raise_read_only()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Writing arrives in Phase 3."""
        self._raise_read_only()

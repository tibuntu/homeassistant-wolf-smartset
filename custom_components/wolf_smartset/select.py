"""Writable list parameters (ControlType 1 and 35)."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WolfConfigEntry, WolfSystemCoordinator
from .entity import WolfEntity, add_entities
from .model import Kind, Parameter

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WolfConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up select entities."""
    add_entities(entry, async_add_entities, (Kind.SELECT,), WolfSelect)


class WolfSelect(WolfEntity, SelectEntity):
    """A list setting; options are the selectable list items."""

    def __init__(self, coordinator: WolfSystemCoordinator, parameter: Parameter) -> None:
        """Options from the description."""
        super().__init__(coordinator, parameter)
        self._attr_options = [parameter.options[v] for v in parameter.selectable]

    @property
    def current_option(self) -> str | None:
        """Display text of the current value, if it is selectable."""
        text = self.parameter.options.get(self.raw_value or "")
        return text if text in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        """Write the list value behind the display text."""
        options = self.parameter.options
        value = next((v for v in self.parameter.selectable if options[v] == option), option)
        await self._async_write(value)

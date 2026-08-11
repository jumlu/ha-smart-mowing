"""Switch entity for Smart Mowing (master automatic on/off)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import SmartMowingCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartMowingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AutomaticSwitch(coordinator, entry)])


class AutomaticSwitch(SwitchEntity, RestoreEntity):
    """Master switch: when off, the integration never acts on the mower."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "automatic"
    _attr_icon = "mdi:robot-mower"

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._entry = entry
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{entry.entry_id}_automatic"

    async def async_added_to_hass(self) -> None:
        self.coordinator.add_update_listener(self._handle_update)
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self.coordinator.restore_automatic_enabled(last_state.state == "on")

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.automatic_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_automatic_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_automatic_enabled(False)

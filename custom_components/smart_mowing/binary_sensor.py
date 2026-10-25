"""Binary sensor entities for Smart Mowing."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SmartMowingConfigEntry
from .coordinator import SmartMowingCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartMowingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            MowingAllowedBinarySensor(coordinator, entry),
            GrassWetBinarySensor(coordinator, entry),
            DormantBinarySensor(coordinator, entry),
        ]
    )


class _BaseBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._entry = entry
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        self.coordinator.add_update_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class MowingAllowedBinarySensor(_BaseBinarySensor):
    """Whether mowing is currently allowed (all blockers cleared)."""

    _attr_translation_key = "mowing_allowed"
    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_mowing_allowed"

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.mow_allowed

    @property
    def extra_state_attributes(self) -> dict:
        return {"blockers": self.coordinator.state.active_blockers}


class GrassWetBinarySensor(_BaseBinarySensor):
    """Standalone wetness assessment (rain / dew / recent rain)."""

    _attr_translation_key = "grass_wet"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_grass_wet"

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.wet


class DormantBinarySensor(_BaseBinarySensor):
    """Winter dormancy: the lawn has stopped growing, time to winterize the mower."""

    _attr_translation_key = "dormant"
    _attr_icon = "mdi:snowflake"

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_dormant"

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.dormant

    @property
    def extra_state_attributes(self) -> dict:
        rate = self.coordinator.state.growth_rate_estimate
        return {
            "streak_days": self.coordinator.state.dormancy_streak_days,
            "growth_rate_mm_per_day": round(rate, 3) if rate is not None else None,
        }

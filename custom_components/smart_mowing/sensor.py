"""Sensor entities for Smart Mowing."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
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
    async_add_entities(
        [
            GrowthIndexSensor(coordinator, entry),
            MowNeedSensor(coordinator, entry),
            LastMowSensor(coordinator, entry),
            NextMowSensor(coordinator, entry),
        ]
    )


class _BaseSensor(SensorEntity):
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


class GrowthIndexSensor(_BaseSensor, RestoreEntity):
    """Accumulated Growing Degree Days since the last mow."""

    _attr_translation_key = "growth_index"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "GDD"
    _attr_icon = "mdi:sprout"

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_growth_index"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable"):
            try:
                self.coordinator.restore_growth_index(float(last_state.state))
            except ValueError:
                pass

    @property
    def native_value(self) -> float:
        return round(self.coordinator.state.growth_index, 2)


class MowNeedSensor(_BaseSensor):
    """Mowing need as a percentage of the configured threshold."""

    _attr_translation_key = "mow_need"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:content-cut"

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_mow_need"

    @property
    def native_value(self) -> float:
        return round(self.coordinator.state.need_percent, 1)


class LastMowSensor(_BaseSensor, RestoreEntity):
    """Timestamp of the last completed mow started by this integration."""

    _attr_translation_key = "last_mow"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:history"

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_mow"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable"):
            try:
                self.coordinator.restore_last_mow_time(datetime.fromisoformat(last_state.state))
            except ValueError:
                pass

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.state.last_mow_time


class NextMowSensor(_BaseSensor):
    """Forecast timestamp of the next expected mow."""

    _attr_translation_key = "next_mow"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_mow"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.state.next_mow_time

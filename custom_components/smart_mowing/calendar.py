"""Calendar entity for Smart Mowing: the forecast next mow as an all-day event."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SmartMowingConfigEntry
from .coordinator import SmartMowingCoordinator

EVENT_SUMMARY = {"de": "Mähen geplant", "en": "Mow planned"}


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartMowingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([MowPlanCalendar(entry.runtime_data, entry)])


class MowPlanCalendar(CalendarEntity):
    """Shows the next forecast mow (sensor next_mow) as a single all-day event.

    The event moves with the forecast, which a calendar written to by an
    automation can't do - HA has no action to move or delete an event.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "mow_plan"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: SmartMowingCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_mow_plan"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        self.coordinator.add_update_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _planned_event(self) -> CalendarEvent | None:
        planned = self.coordinator.state.next_mow_time
        if planned is None:
            return None
        local = dt_util.as_local(planned)
        language = self.coordinator.calendar_language
        need = round(self.coordinator.need_percent)
        return CalendarEvent(
            start=local.date(),
            end=local.date() + timedelta(days=1),
            summary=EVENT_SUMMARY.get(language, EVENT_SUMMARY["en"]),
            description=f"{local.strftime('%H:%M')} · {need} %",
        )

    @property
    def event(self) -> CalendarEvent | None:
        return self._planned_event()

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        event = self._planned_event()
        if event is None:
            return []
        event_start = dt_util.start_of_local_day(event.start)
        event_end = event_start + timedelta(days=1)
        if event_end <= start_date or event_start >= end_date:
            return []
        return [event]

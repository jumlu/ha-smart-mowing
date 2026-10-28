"""Tests for the mow plan calendar."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_mowing.const import (
    CONF_MOW_WINDOW_END,
    CONF_MOW_WINDOW_START,
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_RELEASE_GRACE_MINUTES,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
)

MOWER_ENTITY = "lawn_mower.test_mower"
TEMP_ENTITY = "sensor.test_temperature"
CALENDAR_ENTITY = "calendar.front_lawn_mow_plan"

# 12:00 local (US/Pacific, the test harness time zone)
NOON = "2026-10-20 19:00:00+00:00"


async def _setup(hass) -> MockConfigEntry:
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "15")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "Front Lawn",
            CONF_MOWER_ENTITY: MOWER_ENTITY,
            CONF_TEMPERATURE_ENTITY: TEMP_ENTITY,
        },
        options={
            CONF_MOW_WINDOW_START: "00:00:00",
            CONF_MOW_WINDOW_END: "23:59:59",
            CONF_RELEASE_GRACE_MINUTES: 0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data.state.automatic_enabled = False
    return entry


async def _get_events(hass, start, end) -> list[dict]:
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {"entity_id": CALENDAR_ENTITY, "start_date_time": start, "end_date_time": end},
        blocking=True,
        return_response=True,
    )
    return response[CALENDAR_ENTITY]["events"]


async def test_planned_mow_is_an_all_day_event_on_the_forecast_date(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.growth_index = 10.0
    coordinator.state.growth_baseline = 10.0
    coordinator.state.growth_rate_estimate = 0.25
    await coordinator._async_evaluate()

    planned = dt_util.as_local(coordinator.state.next_mow_time).date()
    now = dt_util.now()
    events = await _get_events(hass, now, now + timedelta(days=30))

    assert len(events) == 1
    assert events[0]["start"] == planned.isoformat()
    assert events[0]["end"] == (planned + timedelta(days=1)).isoformat()
    assert events[0]["summary"] == "Mow planned"


async def test_event_moves_with_the_forecast(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.growth_index = 10.0
    coordinator.state.growth_baseline = 7.0
    coordinator.state.growth_rate_estimate = 0.25
    await coordinator._async_evaluate()
    first = dt_util.as_local(coordinator.state.next_mow_time).date()

    coordinator.state.growth_baseline = 10.0
    await coordinator._async_evaluate()

    now = dt_util.now()
    events = await _get_events(hass, now, now + timedelta(days=30))
    assert len(events) == 1
    assert events[0]["start"] != first.isoformat()


async def test_no_event_outside_requested_range_or_without_forecast(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.growth_index = 10.0
    coordinator.state.growth_baseline = 10.0
    coordinator.state.growth_rate_estimate = 0.25
    await coordinator._async_evaluate()

    now = dt_util.now()
    assert await _get_events(hass, now, now + timedelta(days=2)) == []

    coordinator.state.growth_rate_estimate = 0.0
    hass.states.async_set(TEMP_ENTITY, "unavailable")
    coordinator.state.daily_temp_count = 0
    await coordinator._async_evaluate()
    assert coordinator.state.next_mow_time is None
    assert await _get_events(hass, now, now + timedelta(days=60)) == []
    assert hass.states.get(CALENDAR_ENTITY).state == "off"

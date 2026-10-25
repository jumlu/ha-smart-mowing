"""Tests for the frost lockout and winter dormancy."""

from __future__ import annotations

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_mowing.const import (
    BLOCKER_DORMANT,
    BLOCKER_FROST,
    CONF_DORMANCY_PAUSES_AUTOMATIC,
    CONF_MOW_WINDOW_END,
    CONF_MOW_WINDOW_START,
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_RELEASE_GRACE_MINUTES,
    CONF_TEMPERATURE_ENTITY,
    DEFAULT_DORMANCY_DAYS,
    DOMAIN,
    EVENT_DORMANCY_CHANGED,
    STORAGE_VERSION,
)
from custom_components.smart_mowing.coordinator import SmartMowingCoordinator

MOWER_ENTITY = "lawn_mower.test_mower"
TEMP_ENTITY = "sensor.test_temperature"
DORMANT_ENTITY = "binary_sensor.front_lawn_winter_dormancy"
ENTRY_ID = "test_entry_id"

FULL_DAY = {
    CONF_MOW_WINDOW_START: "00:00:00",
    CONF_MOW_WINDOW_END: "23:59:59",
    CONF_RELEASE_GRACE_MINUTES: 0,
}


def _make_entry(hass, options=None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=ENTRY_ID,
        data={
            CONF_NAME: "Front Lawn",
            CONF_MOWER_ENTITY: MOWER_ENTITY,
            CONF_TEMPERATURE_ENTITY: TEMP_ENTITY,
        },
        options={**FULL_DAY, **(options or {})},
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, options=None) -> MockConfigEntry:
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "15")
    entry = _make_entry(hass, options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _roll_days(coordinator: SmartMowingCoordinator, avg_temp: float, days: int) -> None:
    for _ in range(days):
        coordinator.state.daily_temp_sum = avg_temp
        coordinator.state.daily_temp_count = 1
        coordinator._roll_over_day()


# ---------------------------------------------------------------- frost


async def test_frost_blocks_with_hysteresis(hass):
    entry = _make_entry(hass)
    coordinator = SmartMowingCoordinator(hass, entry)
    hass.states.async_set(MOWER_ENTITY, "docked")
    now = dt_util.utcnow()

    hass.states.async_set(TEMP_ENTITY, "3.5")
    assert BLOCKER_FROST in coordinator._compute_blockers(now)

    # 4.2 °C is above the 4 °C threshold but within the 0.5 °C hysteresis
    hass.states.async_set(TEMP_ENTITY, "4.2")
    assert BLOCKER_FROST in coordinator._compute_blockers(now)

    hass.states.async_set(TEMP_ENTITY, "4.6")
    assert BLOCKER_FROST not in coordinator._compute_blockers(now)

    hass.states.async_set(TEMP_ENTITY, "4.2")
    assert BLOCKER_FROST not in coordinator._compute_blockers(now)


# -------------------------------------------------------------- dormancy


async def test_cold_days_enter_dormancy_and_fire_event(hass):
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    events = []
    hass.bus.async_listen(EVENT_DORMANCY_CHANGED, events.append)

    # 2 °C average: ~0.01 mm/day, far below the 0.1 mm/day threshold
    _roll_days(coordinator, 2.0, DEFAULT_DORMANCY_DAYS - 1)
    assert coordinator.state.dormant is False
    assert coordinator.state.dormancy_streak_days == DEFAULT_DORMANCY_DAYS - 1

    _roll_days(coordinator, 2.0, 1)
    await hass.async_block_till_done()
    assert coordinator.state.dormant is True
    assert len(events) == 1
    assert events[0].data["dormant"] is True

    await coordinator._async_evaluate()
    assert hass.states.get(DORMANT_ENTITY).state == "on"


async def test_single_warm_day_resets_the_streak(hass):
    entry = await _setup(hass)
    coordinator = entry.runtime_data

    _roll_days(coordinator, 2.0, DEFAULT_DORMANCY_DAYS - 1)
    _roll_days(coordinator, 15.0, 1)
    _roll_days(coordinator, 2.0, DEFAULT_DORMANCY_DAYS - 1)

    assert coordinator.state.dormant is False


async def test_growth_in_spring_leaves_dormancy(hass):
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    _roll_days(coordinator, 2.0, DEFAULT_DORMANCY_DAYS)
    assert coordinator.state.dormant is True

    # one mild day mid-winter does not end it
    _roll_days(coordinator, 12.0, 1)
    _roll_days(coordinator, 2.0, 1)
    assert coordinator.state.dormant is True

    _roll_days(coordinator, 12.0, DEFAULT_DORMANCY_DAYS)
    assert coordinator.state.dormant is False


async def test_dormancy_only_informs_by_default(hass):
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.dormant = True

    blockers = coordinator._compute_blockers(dt_util.utcnow())

    assert BLOCKER_DORMANT not in blockers


async def test_dormancy_pauses_automatic_when_enabled(hass):
    entry = await _setup(hass, options={CONF_DORMANCY_PAUSES_AUTOMATIC: True})
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.dormant = True
    coordinator.state.growth_index = 5.0
    coordinator.state.growth_baseline = 0.0

    await coordinator._async_evaluate()

    assert BLOCKER_DORMANT in coordinator.state.active_blockers
    assert coordinator.state.mow_allowed is False
    assert coordinator.state.next_mow_time is None


async def test_dormancy_survives_restart(hass, hass_storage):
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}.{ENTRY_ID}",
        "data": {
            "growth_index": 60.0,
            "growth_baseline": 59.0,
            "growth_rate_estimate": 0.02,
            "last_mow_time": None,
            "dormant": True,
            "dormancy_streak_days": 2,
        },
    }

    entry = await _setup(hass)

    assert entry.runtime_data.state.dormant is True
    assert entry.runtime_data.state.dormancy_streak_days == 2
    assert hass.states.get(DORMANT_ENTITY).state == "on"

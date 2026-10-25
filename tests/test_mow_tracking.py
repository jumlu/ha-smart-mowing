"""Tests for mow detection, the growth baseline, persistence and the forecast."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytest
from homeassistant.core import State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.smart_mowing.const import (
    CONF_MOW_WINDOW_END,
    CONF_MOW_WINDOW_START,
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_RELEASE_GRACE_MINUTES,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
    EVENT_MOWING_STARTED,
    MOW_START_MAX_ATTEMPTS,
    MOW_START_RETRY_BACKOFF_MINUTES,
    MOW_START_TIMEOUT_MINUTES,
    STORAGE_VERSION,
)
from custom_components.smart_mowing.coordinator import compute_need_percent

MOWER_ENTITY = "lawn_mower.test_mower"
TEMP_ENTITY = "sensor.test_temperature"
MOW_NEED_ENTITY = "sensor.front_lawn_mow_need"
GROWTH_ENTITY = "sensor.front_lawn_growth_index"
LAST_MOW_ENTITY = "sensor.front_lawn_last_mow"
ENTRY_ID = "test_entry_id"

# 12:00 local (US/Pacific, the test harness time zone) on a Tuesday
NOON = "2026-10-20 19:00:00+00:00"

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
        options=FULL_DAY if options is None else options,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, options=None, mower_state="docked") -> MockConfigEntry:
    hass.states.async_set(MOWER_ENTITY, mower_state)
    hass.states.async_set(TEMP_ENTITY, "15")
    entry = _make_entry(hass, options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _set_mower(hass, state: str) -> None:
    hass.states.async_set(MOWER_ENTITY, state)
    await hass.async_block_till_done()


def _register_start_service(hass) -> list:
    calls: list = []

    async def _start(call):
        calls.append(call)

    hass.services.async_register("lawn_mower", "start_mowing", _start)
    return calls


# ----------------------------------------------------------------- need


@pytest.mark.parametrize(
    ("growth", "threshold", "expected"),
    [
        (0.0, 4.0, 0.0),
        (1.0, 4.0, 25.0),
        (4.0, 4.0, 100.0),
        (57.0, 4.0, 200.0),  # capped
        (-1.0, 4.0, 0.0),
        (1.0, 0.0, 0.0),
    ],
)
def test_compute_need_percent(growth, threshold, expected):
    assert compute_need_percent(growth, threshold) == pytest.approx(expected)


async def test_need_is_measured_against_baseline(hass):
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 57.04
    coordinator.state.growth_baseline = 55.04

    await coordinator._async_evaluate()

    assert coordinator.need_percent == pytest.approx(50.0)
    assert hass.states.get(MOW_NEED_ENTITY).state == "50.0"
    assert coordinator.state.mow_needed is False


async def test_baseline_resets_when_mower_starts_mowing(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 60.0
    coordinator.state.growth_baseline = 50.0
    await coordinator._async_evaluate()
    assert hass.states.get(MOW_NEED_ENTITY).state == "200.0"

    await _set_mower(hass, "mowing")

    assert coordinator.state.growth_baseline == 60.0
    assert coordinator.state.last_mow_time == dt_util.utcnow()
    assert hass.states.get(MOW_NEED_ENTITY).state == "0.0"
    assert hass.states.get(LAST_MOW_ENTITY).state == dt_util.utcnow().isoformat()

    # more growth after the mow shows up as need again
    coordinator.state.growth_index = 61.0
    await coordinator._async_evaluate()
    assert hass.states.get(MOW_NEED_ENTITY).state == "25.0"


async def test_manual_app_run_also_resets_baseline(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 10.0
    coordinator.state.growth_baseline = 0.0
    started = []
    hass.bus.async_listen(EVENT_MOWING_STARTED, started.append)

    await _set_mower(hass, "mowing")

    assert coordinator.state.growth_baseline == 10.0
    assert coordinator.state.mower_started_by_us is False
    # smart_mowing_started is reserved for runs this integration started
    assert started == []


async def test_paused_to_mowing_is_not_a_new_mow(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    await _set_mower(hass, "mowing")
    first_mow = coordinator.state.last_mow_time

    await _set_mower(hass, "paused")
    freezer.tick(timedelta(hours=1))
    coordinator.state.growth_index += 1.0
    await _set_mower(hass, "mowing")

    assert coordinator.state.last_mow_time == first_mow
    assert coordinator.state.growth_baseline == coordinator.state.growth_index - 1.0


# ------------------------------------------------------ start confirmation


async def test_start_command_without_mowing_state_is_not_counted(hass, freezer, caplog):
    freezer.move_to(NOON)
    calls = _register_start_service(hass)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.growth_index = 8.0
    coordinator.state.growth_baseline = 0.0

    await coordinator._async_evaluate()
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert coordinator.state.pending_start_since is not None
    assert coordinator.state.last_mow_time is None
    assert coordinator.state.growth_baseline == 0.0
    assert hass.states.get(LAST_MOW_ENTITY).state == "unknown"

    # still docked: further evaluations while pending must not re-send
    await coordinator._async_evaluate()
    assert len(calls) == 1

    caplog.set_level(logging.WARNING)
    freezer.tick(timedelta(minutes=MOW_START_TIMEOUT_MINUTES + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert coordinator.state.pending_start_since is None
    assert coordinator.state.start_failures == 1
    assert coordinator.state.last_mow_time is None
    assert coordinator.need_percent == 200.0
    assert "did not report mowing" in caplog.text
    # backoff: no new attempt right after the timeout
    assert len(calls) == 1

    freezer.tick(timedelta(minutes=MOW_START_RETRY_BACKOFF_MINUTES + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls) == 2


async def test_start_attempts_give_up_after_max(hass, freezer, caplog):
    freezer.move_to(NOON)
    calls = _register_start_service(hass)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.growth_index = 8.0
    coordinator.state.growth_baseline = 0.0
    await coordinator._async_evaluate()
    await hass.async_block_till_done()

    for _ in range(MOW_START_MAX_ATTEMPTS):
        freezer.tick(timedelta(minutes=MOW_START_TIMEOUT_MINUTES + 1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        freezer.tick(timedelta(minutes=MOW_START_RETRY_BACKOFF_MINUTES + 1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert len(calls) == MOW_START_MAX_ATTEMPTS
    assert coordinator.state.start_failures == MOW_START_MAX_ATTEMPTS
    assert coordinator.state.start_retry_after > dt_util.utcnow()
    assert "not retrying before" in caplog.text


async def test_start_command_counts_once_mower_reports_mowing(hass, freezer):
    freezer.move_to(NOON)
    calls = _register_start_service(hass)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.growth_index = 8.0
    coordinator.state.growth_baseline = 0.0
    started = []
    hass.bus.async_listen(EVENT_MOWING_STARTED, started.append)

    await coordinator._async_evaluate()
    await hass.async_block_till_done()
    assert len(calls) == 1

    # the mower takes a while to leave the dock (observed ~25 min on Navimow)
    freezer.tick(timedelta(minutes=24))
    await _set_mower(hass, "mowing")

    assert coordinator.state.last_mow_time == dt_util.utcnow()
    assert coordinator.state.growth_baseline == 8.0
    assert coordinator.state.mower_started_by_us is True
    assert coordinator.state.pending_start_since is None
    assert len(started) == 1


# --------------------------------------------------------------- flaps


async def test_flap_counts_only_once(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 10.0
    coordinator.state.growth_baseline = 0.0

    await _set_mower(hass, "mowing")
    first_mow = coordinator.state.last_mow_time

    freezer.tick(timedelta(seconds=5))
    await _set_mower(hass, "docked")
    coordinator.state.growth_index = 10.5
    freezer.tick(timedelta(seconds=5))
    await _set_mower(hass, "mowing")

    assert coordinator.state.last_mow_time == first_mow
    assert coordinator.state.growth_baseline == 10.0


async def test_new_run_after_debounce_counts_again(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False

    await _set_mower(hass, "mowing")
    freezer.tick(timedelta(hours=2))
    await _set_mower(hass, "docked")
    coordinator.state.growth_index += 3.0
    freezer.tick(timedelta(hours=20))
    await _set_mower(hass, "mowing")

    assert coordinator.state.last_mow_time == dt_util.utcnow()
    assert coordinator.state.growth_baseline == coordinator.state.growth_index


async def test_flap_keeps_own_session_ownership(hass, freezer):
    freezer.move_to(NOON)
    _register_start_service(hass)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.growth_index = 8.0
    coordinator.state.growth_baseline = 0.0
    await coordinator._async_evaluate()
    await hass.async_block_till_done()
    await _set_mower(hass, "mowing")
    assert coordinator.state.mower_started_by_us is True

    freezer.tick(timedelta(seconds=3))
    await _set_mower(hass, "docked")
    freezer.tick(timedelta(seconds=3))
    await _set_mower(hass, "mowing")

    assert coordinator.state.mower_started_by_us is True


# --------------------------------------------------------- persistence


def _stored(growth_index, baseline, last_mow=None, rate=None) -> dict:
    return {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}.{ENTRY_ID}",
        "data": {
            "growth_index": growth_index,
            "growth_baseline": baseline,
            "growth_rate_estimate": rate,
            "last_mow_time": last_mow,
        },
    }


async def test_restore_after_restart_without_flicker(hass, hass_storage, freezer):
    freezer.move_to(NOON)
    last_mow = "2026-10-15T19:25:00+00:00"
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = _stored(57.04, 55.04, last_mow, 0.25)

    seen: list[str] = []

    def _record(event):
        if event.data["entity_id"] == MOW_NEED_ENTITY and event.data["new_state"]:
            seen.append(event.data["new_state"].state)

    hass.bus.async_listen("state_changed", _record)

    entry = await _setup(hass)
    coordinator = entry.runtime_data

    assert coordinator.state.growth_baseline == pytest.approx(55.04)
    assert coordinator.state.last_mow_time == datetime.fromisoformat(last_mow)
    assert hass.states.get(GROWTH_ENTITY).state == "57.04"
    # every state the sensor ever wrote is the correct one - no 0 -> 200 jump
    assert seen
    assert set(seen) == {"50.0"}


async def test_store_wins_over_stale_entity_restore(hass, hass_storage):
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = _stored(57.0, 56.0)
    mock_restore_cache(hass, [State(GROWTH_ENTITY, "12.0")])

    entry = await _setup(hass)

    assert entry.runtime_data.state.growth_index == 57.0
    assert entry.runtime_data.state.growth_baseline == 56.0


async def test_upgrade_without_store_starts_need_at_zero(hass):
    # pre-baseline versions only had the cumulative index in entity state
    mock_restore_cache(
        hass,
        [
            State(GROWTH_ENTITY, "57.04"),
            State(LAST_MOW_ENTITY, "2026-10-23T05:43:00+00:00"),
        ],
    )

    entry = await _setup(hass)
    coordinator = entry.runtime_data

    assert coordinator.state.growth_index == pytest.approx(57.04)
    assert coordinator.state.growth_baseline == pytest.approx(57.04)
    assert hass.states.get(MOW_NEED_ENTITY).state == "0.0"


async def test_baseline_is_persisted_across_reload(hass, hass_storage, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 42.0
    await _set_mower(hass, "mowing")

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    data = hass_storage[f"{DOMAIN}.{ENTRY_ID}"]["data"]
    assert data["growth_baseline"] == 42.0
    assert data["last_mow_time"] == dt_util.utcnow().isoformat()
    assert entry.runtime_data.state.growth_baseline == 42.0
    assert entry.runtime_data.state.last_mow_time == dt_util.utcnow()


# ------------------------------------------------------------ forecast


async def test_forecast_below_threshold_uses_growth_rate(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 10.0
    coordinator.state.growth_baseline = 10.0
    coordinator.state.growth_rate_estimate = 0.25

    await coordinator._async_evaluate()

    # 4 mm threshold at 0.25 mm/day -> 16 days
    expected = dt_util.utcnow() + timedelta(days=16)
    assert coordinator.state.next_mow_time == expected


async def test_forecast_falls_back_to_temperature_model(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False

    await coordinator._async_evaluate()

    assert coordinator.state.next_mow_time is not None
    assert coordinator.state.next_mow_time > dt_util.utcnow()


async def test_forecast_at_or_above_threshold_and_allowed_is_now(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 5.0
    coordinator.state.growth_baseline = 0.0

    await coordinator._async_evaluate()

    assert coordinator.state.mow_allowed is True
    assert coordinator.state.next_mow_time == dt_util.utcnow()


async def test_forecast_at_or_above_threshold_outside_window_is_next_window(hass, freezer):
    # 21:00 local, window 07:00-20:00 -> next window opens tomorrow 07:00 local
    freezer.move_to("2026-10-21 04:00:00+00:00")
    entry = await _setup(
        hass,
        options={
            CONF_MOW_WINDOW_START: "07:00:00",
            CONF_MOW_WINDOW_END: "20:00:00",
            CONF_RELEASE_GRACE_MINUTES: 0,
        },
    )
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 5.0
    coordinator.state.growth_baseline = 0.0

    await coordinator._async_evaluate()

    assert coordinator.state.mow_needed is True
    assert coordinator.state.mow_allowed is False
    expected_local = dt_util.as_local(dt_util.utcnow()).replace(
        hour=7, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    assert coordinator.state.next_mow_time == dt_util.as_utc(expected_local)


async def test_forecast_respects_cooldown(hass, freezer):
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    coordinator.state.automatic_enabled = False
    coordinator.state.growth_index = 5.0
    coordinator.state.growth_baseline = 0.0
    coordinator.state.last_mow_time = dt_util.utcnow() - timedelta(hours=2)

    await coordinator._async_evaluate()

    assert coordinator.state.next_mow_time == coordinator.state.last_mow_time + timedelta(hours=20)

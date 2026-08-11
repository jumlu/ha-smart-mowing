"""Tests for individual mowing blockers and hysteresis behaviour."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_mowing.const import (
    BLOCKER_COOLDOWN,
    BLOCKER_DEW,
    BLOCKER_HEAT,
    BLOCKER_OUTSIDE_WINDOW,
    BLOCKER_RAINING,
    BLOCKER_UNAVAILABLE_SOURCE,
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_RAIN_RATE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
)
from custom_components.smart_mowing.coordinator import SmartMowingCoordinator
from homeassistant.util import dt as dt_util

MOWER_ENTITY = "lawn_mower.test_mower"
TEMP_ENTITY = "sensor.test_temperature"
RAIN_RATE_ENTITY = "sensor.test_rain_rate"


def _make_entry(hass, data=None, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "Test Lawn",
            CONF_MOWER_ENTITY: MOWER_ENTITY,
            CONF_TEMPERATURE_ENTITY: TEMP_ENTITY,
            **(data or {}),
        },
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


async def test_unavailable_source_blocks(hass):
    entry = _make_entry(hass)
    coordinator = SmartMowingCoordinator(hass, entry)
    hass.states.async_set(MOWER_ENTITY, "docked")
    # temperature entity missing entirely -> unavailable
    blockers = coordinator._compute_blockers(dt_util.utcnow())
    assert BLOCKER_UNAVAILABLE_SOURCE in blockers


async def test_outside_window_blocks(hass):
    entry = _make_entry(hass)
    coordinator = SmartMowingCoordinator(hass, entry)
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "15")

    now = dt_util.utcnow().replace(hour=3, minute=0, second=0, microsecond=0)
    blockers = coordinator._compute_blockers(now)
    assert BLOCKER_OUTSIDE_WINDOW in blockers


async def test_raining_blocks_with_hysteresis(hass):
    entry = _make_entry(
        hass,
        data={CONF_RAIN_RATE_ENTITY: RAIN_RATE_ENTITY},
    )
    coordinator = SmartMowingCoordinator(hass, entry)
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "15")
    hass.states.async_set(RAIN_RATE_ENTITY, "0.5")

    now = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    blockers = coordinator._compute_blockers(now)
    assert BLOCKER_RAINING in blockers

    # drop just under threshold+hysteresis -> should still be blocked (hysteresis holds)
    hass.states.async_set(RAIN_RATE_ENTITY, "0.22")
    blockers = coordinator._compute_blockers(now)
    assert BLOCKER_RAINING in blockers

    # drop below threshold - hysteresis -> released
    hass.states.async_set(RAIN_RATE_ENTITY, "0.1")
    blockers = coordinator._compute_blockers(now)
    assert BLOCKER_RAINING not in blockers


async def test_cooldown_blocks_after_recent_mow(hass):
    entry = _make_entry(hass)
    coordinator = SmartMowingCoordinator(hass, entry)
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "15")

    now = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    coordinator.state.last_mow_time = now - timedelta(hours=1)
    blockers = coordinator._compute_blockers(now)
    assert BLOCKER_COOLDOWN in blockers

    coordinator.state.last_mow_time = now - timedelta(hours=25)
    blockers = coordinator._compute_blockers(now)
    assert BLOCKER_COOLDOWN not in blockers


async def test_heat_blocks_above_threshold(hass):
    entry = _make_entry(hass)
    coordinator = SmartMowingCoordinator(hass, entry)
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "31")

    now = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    blockers = coordinator._compute_blockers(now)
    assert BLOCKER_HEAT in blockers

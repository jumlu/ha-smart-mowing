"""Tests for the smart_mowing services."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_mowing.const import (
    ATTR_GROWTH_VALUE,
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
    SERVICE_FORCE_MOW,
    SERVICE_RESET_GROWTH,
    SERVICE_SET_GROWTH,
)

MOWER_ENTITY = "lawn_mower.test_mower"
TEMP_ENTITY = "sensor.test_temperature"


async def _setup_entry(hass) -> MockConfigEntry:
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "15")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "Front Lawn",
            CONF_MOWER_ENTITY: MOWER_ENTITY,
            CONF_TEMPERATURE_ENTITY: TEMP_ENTITY,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _growth_sensor_entity_id(hass, entry: MockConfigEntry) -> str:
    registry = er.async_get(hass)
    for e in er.async_entries_for_config_entry(registry, entry.entry_id):
        if e.unique_id == f"{entry.entry_id}_growth_index":
            return e.entity_id
    raise AssertionError("growth index sensor not found")


async def test_reset_growth_service(hass):
    entry = await _setup_entry(hass)
    entry.runtime_data.state.growth_index = 42.0
    entity_id = _growth_sensor_entity_id(hass, entry)

    await hass.services.async_call(
        DOMAIN, SERVICE_RESET_GROWTH, {"entity_id": entity_id}, blocking=True
    )
    assert entry.runtime_data.state.growth_index == 0.0


async def test_set_growth_service(hass):
    entry = await _setup_entry(hass)
    entity_id = _growth_sensor_entity_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_GROWTH,
        {"entity_id": entity_id, ATTR_GROWTH_VALUE: 30.0},
        blocking=True,
    )
    assert entry.runtime_data.state.growth_index == 30.0


async def test_force_mow_service_starts_mower(hass):
    entry = await _setup_entry(hass)
    entity_id = _growth_sensor_entity_id(hass, entry)

    calls = []

    async def _mock_start_mowing(call):
        calls.append(call)

    hass.services.async_register("lawn_mower", "start_mowing", _mock_start_mowing)

    await hass.services.async_call(
        DOMAIN, SERVICE_FORCE_MOW, {"entity_id": entity_id}, blocking=True
    )
    assert len(calls) == 1
    assert entry.runtime_data.state.mower_started_by_us is True

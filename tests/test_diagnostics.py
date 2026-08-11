"""Tests for the diagnostics platform."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_mowing.const import (
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
)
from custom_components.smart_mowing.diagnostics import async_get_config_entry_diagnostics

MOWER_ENTITY = "lawn_mower.test_mower"
TEMP_ENTITY = "sensor.test_temperature"


async def test_diagnostics_contains_runtime_state(hass):
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

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["source_entities"]["mower_entity"] == MOWER_ENTITY
    assert diagnostics["source_values"]["mower_entity"] == "docked"
    assert "growth_index" in diagnostics["runtime_state"]
    assert "active_blockers" in diagnostics["runtime_state"]

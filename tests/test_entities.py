"""Integration tests for sensor/binary_sensor/switch entities and setup/unload."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_mowing.const import (
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
)

MOWER_ENTITY = "lawn_mower.test_mower"
TEMP_ENTITY = "sensor.test_temperature"

EXPECTED_UNIQUE_ID_SUFFIXES = [
    "_growth_index",
    "_mow_need",
    "_last_mow",
    "_next_mow",
    "_mowing_allowed",
    "_grass_wet",
    "_automatic",
]


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


def _entity_ids_for_entry(hass, entry: MockConfigEntry) -> dict[str, str]:
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    return {e.unique_id: e.entity_id for e in entries}


async def test_setup_creates_all_entities(hass):
    entry = await _setup_entry(hass)
    by_unique_id = _entity_ids_for_entry(hass, entry)

    assert len(by_unique_id) == len(EXPECTED_UNIQUE_ID_SUFFIXES)
    for suffix in EXPECTED_UNIQUE_ID_SUFFIXES:
        unique_id = f"{entry.entry_id}{suffix}"
        assert unique_id in by_unique_id, f"missing entity with unique_id {unique_id}"
        state = hass.states.get(by_unique_id[unique_id])
        assert state is not None
        assert state.state not in ("unknown", "unavailable")


async def test_mowing_allowed_blockers_attribute(hass):
    entry = await _setup_entry(hass)
    by_unique_id = _entity_ids_for_entry(hass, entry)
    entity_id = by_unique_id[f"{entry.entry_id}_mowing_allowed"]

    state = hass.states.get(entity_id)
    assert "blockers" in state.attributes
    assert isinstance(state.attributes["blockers"], list)


async def test_automatic_switch_toggle(hass):
    entry = await _setup_entry(hass)
    by_unique_id = _entity_ids_for_entry(hass, entry)
    switch_entity_id = by_unique_id[f"{entry.entry_id}_automatic"]

    assert hass.states.get(switch_entity_id).state == "on"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch_entity_id}, blocking=True
    )
    assert hass.states.get(switch_entity_id).state == "off"
    assert entry.runtime_data.state.automatic_enabled is False


async def test_unload_entry(hass):
    entry = await _setup_entry(hass)
    by_unique_id = _entity_ids_for_entry(hass, entry)
    growth_entity_id = by_unique_id[f"{entry.entry_id}_growth_index"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(growth_entity_id) is None

"""Tests for the Smart Mowing config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_mowing.const import (
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
)

MOWER_ENTITY = "lawn_mower.test_mower"
TEMP_ENTITY = "sensor.test_temperature"
OTHER_MOWER_ENTITY = "lawn_mower.other_mower"


async def test_full_flow_minimal(hass):
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "15")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Front Lawn",
            CONF_MOWER_ENTITY: MOWER_ENTITY,
            CONF_TEMPERATURE_ENTITY: TEMP_ENTITY,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "weather"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "irrigation"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Front Lawn"
    assert result["data"][CONF_MOWER_ENTITY] == MOWER_ENTITY


async def test_duplicate_name_aborts(hass):
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(TEMP_ENTITY, "15")

    async def _run_flow():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Front Lawn",
                CONF_MOWER_ENTITY: MOWER_ENTITY,
                CONF_TEMPERATURE_ENTITY: TEMP_ENTITY,
            },
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        return await hass.config_entries.flow.async_configure(result["flow_id"], {})

    first = await _run_flow()
    assert first["type"] is FlowResultType.CREATE_ENTRY

    second = await _run_flow()
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_configured"


async def test_reconfigure_updates_existing_entry(hass):
    hass.states.async_set(MOWER_ENTITY, "docked")
    hass.states.async_set(OTHER_MOWER_ENTITY, "docked")
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

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # pre-filled with the entry's current data (as a UI suggested_value, not
    # a voluptuous default, so it doesn't get re-validated when left blank)
    mower_key = next(k for k in result["data_schema"].schema if k == CONF_MOWER_ENTITY)
    assert mower_key.description == {"suggested_value": MOWER_ENTITY}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Front Lawn",
            CONF_MOWER_ENTITY: OTHER_MOWER_ENTITY,
            CONF_TEMPERATURE_ENTITY: TEMP_ENTITY,
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_MOWER_ENTITY] == OTHER_MOWER_ENTITY

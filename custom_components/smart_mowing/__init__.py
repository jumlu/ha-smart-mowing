"""The Smart Mowing integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    ATTR_GROWTH_VALUE,
    DOMAIN,
    PLATFORMS,
    SERVICE_FORCE_MOW,
    SERVICE_RESET_GROWTH,
    SERVICE_SET_GROWTH,
)
from .coordinator import SmartMowingCoordinator

type SmartMowingConfigEntry = ConfigEntry[SmartMowingCoordinator]

SERVICE_ENTITY_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_id})
SERVICE_SET_GROWTH_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required(ATTR_GROWTH_VALUE): vol.Coerce(float),
    }
)


def _coordinator_for_entity(hass: HomeAssistant, entity_id: str) -> SmartMowingCoordinator | None:
    registry = er.async_get(hass)
    entity_entry = registry.async_get(entity_id)
    if entity_entry is None or entity_entry.config_entry_id is None:
        return None
    config_entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
    if config_entry is None:
        return None
    return config_entry.runtime_data


async def async_setup_entry(hass: HomeAssistant, entry: SmartMowingConfigEntry) -> bool:
    """Set up Smart Mowing from a config entry."""
    coordinator = SmartMowingCoordinator(hass, entry)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_setup()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartMowingConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_unload()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: SmartMowingConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_FORCE_MOW):
        return

    async def _handle_force_mow(call: ServiceCall) -> None:
        coordinator = _coordinator_for_entity(hass, call.data["entity_id"])
        if coordinator:
            await coordinator.async_force_mow()

    async def _handle_reset_growth(call: ServiceCall) -> None:
        coordinator = _coordinator_for_entity(hass, call.data["entity_id"])
        if coordinator:
            coordinator.reset_growth()
            coordinator.notify_listeners()

    async def _handle_set_growth(call: ServiceCall) -> None:
        coordinator = _coordinator_for_entity(hass, call.data["entity_id"])
        if coordinator:
            coordinator.set_growth(call.data[ATTR_GROWTH_VALUE])
            coordinator.notify_listeners()

    hass.services.async_register(
        DOMAIN, SERVICE_FORCE_MOW, _handle_force_mow, schema=SERVICE_ENTITY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_GROWTH, _handle_reset_growth, schema=SERVICE_ENTITY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_GROWTH, _handle_set_growth, schema=SERVICE_SET_GROWTH_SCHEMA
    )

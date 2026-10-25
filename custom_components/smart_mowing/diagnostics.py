"""Diagnostics support for Smart Mowing."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import SmartMowingConfigEntry

TO_REDACT: set[str] = set()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SmartMowingConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data

    source_entities = {
        "mower_entity": coordinator.mower_entity_id,
        "temperature_entity": coordinator.temperature_entity_id,
        "rain_rate_entity": coordinator.rain_rate_entity_id,
        "rain_amount_entity": coordinator.rain_amount_entity_id,
        "humidity_entity": coordinator.humidity_entity_id,
        "dewpoint_entity": coordinator.dewpoint_entity_id,
        "soil_moisture_entity": coordinator.soil_moisture_entity_id,
        "solar_radiation_entity": coordinator.solar_radiation_entity_id,
        "irrigation_entities": coordinator.irrigation_entity_ids,
    }
    source_values = {
        key: (state.state if (state := hass.states.get(entity_id)) else None)
        for key, entity_id in source_entities.items()
        if isinstance(entity_id, str)
    }

    return {
        "config_entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "source_entities": source_entities,
        "source_values": source_values,
        "runtime_state": {
            "growth_index": coordinator.state.growth_index,
            "growth_baseline": coordinator.state.growth_baseline,
            "growth_since_mow": coordinator.growth_since_mow,
            "growth_rate_estimate": coordinator.state.growth_rate_estimate,
            "dormant": coordinator.state.dormant,
            "dormancy_streak_days": coordinator.state.dormancy_streak_days,
            "need_percent": coordinator.state.need_percent,
            "mow_needed": coordinator.state.mow_needed,
            "mow_allowed": coordinator.state.mow_allowed,
            "active_blockers": coordinator.state.active_blockers,
            "wet": coordinator.state.wet,
            "last_mow_time": coordinator.state.last_mow_time.isoformat()
            if coordinator.state.last_mow_time
            else None,
            "next_mow_time": coordinator.state.next_mow_time.isoformat()
            if coordinator.state.next_mow_time
            else None,
            "automatic_enabled": coordinator.state.automatic_enabled,
            "mower_started_by_us": coordinator.state.mower_started_by_us,
            "pending_start_since": coordinator.state.pending_start_since.isoformat()
            if coordinator.state.pending_start_since
            else None,
            "start_failures": coordinator.state.start_failures,
            "start_retry_after": coordinator.state.start_retry_after.isoformat()
            if coordinator.state.start_retry_after
            else None,
            "daily_temp_sum": coordinator.state.daily_temp_sum,
            "daily_temp_count": coordinator.state.daily_temp_count,
        },
    }

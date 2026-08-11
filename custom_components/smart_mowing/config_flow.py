"""Config flow for Smart Mowing."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOWED_WEEKDAYS,
    CONF_DEWPOINT_ENTITY,
    CONF_DEWPOINT_SPREAD_MIN,
    CONF_DROUGHT_NO_RAIN_DAYS,
    CONF_DROUGHT_SOIL_MOISTURE_THRESHOLD,
    CONF_GDD_BASE_TEMP,
    CONF_GDD_THRESHOLD,
    CONF_HEAT_LOCKOUT_TEMP,
    CONF_HUMIDITY_ENTITY,
    CONF_HYSTERESIS_DEWPOINT,
    CONF_HYSTERESIS_SOIL_MOISTURE,
    CONF_HYSTERESIS_TEMP,
    CONF_IRRIGATION_ENTITIES,
    CONF_IRRIGATION_LOCKOUT_HOURS,
    CONF_MIN_MOW_INTERVAL_HOURS,
    CONF_MOW_WINDOW_END,
    CONF_MOW_WINDOW_START,
    CONF_MOWER_ENTITY,
    CONF_NAME,
    CONF_ONLY_DOCK_OWN_RUNS,
    CONF_RAIN_AMOUNT_ENTITY,
    CONF_RAIN_RATE_ENTITY,
    CONF_RAIN_STOP_THRESHOLD,
    CONF_RECENT_RAIN_HOURS,
    CONF_RECENT_RAIN_THRESHOLD,
    CONF_RELEASE_GRACE_MINUTES,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOLAR_RADIATION_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    DEFAULT_ALLOWED_WEEKDAYS,
    DEFAULT_DEWPOINT_SPREAD_MIN,
    DEFAULT_DROUGHT_NO_RAIN_DAYS,
    DEFAULT_DROUGHT_SOIL_MOISTURE_THRESHOLD,
    DEFAULT_GDD_BASE_TEMP,
    DEFAULT_GDD_THRESHOLD,
    DEFAULT_HEAT_LOCKOUT_TEMP,
    DEFAULT_HYSTERESIS_DEWPOINT,
    DEFAULT_HYSTERESIS_SOIL_MOISTURE,
    DEFAULT_HYSTERESIS_TEMP,
    DEFAULT_IRRIGATION_LOCKOUT_HOURS,
    DEFAULT_MIN_MOW_INTERVAL_HOURS,
    DEFAULT_MOW_WINDOW_END,
    DEFAULT_MOW_WINDOW_START,
    DEFAULT_ONLY_DOCK_OWN_RUNS,
    DEFAULT_RAIN_STOP_THRESHOLD,
    DEFAULT_RECENT_RAIN_HOURS,
    DEFAULT_RECENT_RAIN_THRESHOLD,
    DEFAULT_RELEASE_GRACE_MINUTES,
    DOMAIN,
)

WEEKDAY_OPTIONS = [
    selector.SelectOptionDict(value="0", label="Monday"),
    selector.SelectOptionDict(value="1", label="Tuesday"),
    selector.SelectOptionDict(value="2", label="Wednesday"),
    selector.SelectOptionDict(value="3", label="Thursday"),
    selector.SelectOptionDict(value="4", label="Friday"),
    selector.SelectOptionDict(value="5", label="Saturday"),
    selector.SelectOptionDict(value="6", label="Sunday"),
]


def _suggest(defaults: dict[str, Any], key: str) -> dict[str, Any]:
    """Build a `description` kwarg that pre-fills a field without forcing
    voluptuous to validate a default value when the field is left empty."""
    if key not in defaults or defaults[key] is None:
        return {}
    return {"description": {"suggested_value": defaults[key]}}


def _step_user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, **_suggest(defaults, CONF_NAME)): selector.TextSelector(),
            vol.Required(
                CONF_MOWER_ENTITY, **_suggest(defaults, CONF_MOWER_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="lawn_mower")),
            vol.Required(
                CONF_TEMPERATURE_ENTITY, **_suggest(defaults, CONF_TEMPERATURE_ENTITY)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
        }
    )


def _step_weather_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_RAIN_RATE_ENTITY, **_suggest(defaults, CONF_RAIN_RATE_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_RAIN_AMOUNT_ENTITY, **_suggest(defaults, CONF_RAIN_AMOUNT_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_HUMIDITY_ENTITY, **_suggest(defaults, CONF_HUMIDITY_ENTITY)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
            ),
            vol.Optional(
                CONF_DEWPOINT_ENTITY, **_suggest(defaults, CONF_DEWPOINT_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SOIL_MOISTURE_ENTITY, **_suggest(defaults, CONF_SOIL_MOISTURE_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SOLAR_RADIATION_ENTITY, **_suggest(defaults, CONF_SOLAR_RADIATION_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        }
    )


def _step_irrigation_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_IRRIGATION_ENTITIES, **_suggest(defaults, CONF_IRRIGATION_ENTITIES)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["switch", "binary_sensor", "valve"], multiple=True
                )
            ),
            vol.Optional(
                CONF_IRRIGATION_LOCKOUT_HOURS,
                default=defaults.get(
                    CONF_IRRIGATION_LOCKOUT_HOURS, DEFAULT_IRRIGATION_LOCKOUT_HOURS
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=48, step=0.5, unit_of_measurement="h")
            ),
        }
    )


class SmartMowingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Mowing."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> Any:
        """Start reconfiguration, pre-filled with the entry's current data."""
        self._data = dict(self._get_reconfigure_entry().data)
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_weather()
        return self.async_show_form(
            step_id="user", data_schema=_step_user_schema(self._data), errors=errors
        )

    async def async_step_weather(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_irrigation()
        return self.async_show_form(step_id="weather", data_schema=_step_weather_schema(self._data))

    async def async_step_irrigation(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            self._data.update(user_input)
            if self.source == SOURCE_RECONFIGURE:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(), data=self._data
                )
            await self.async_set_unique_id(f"{DOMAIN}_{self._data[CONF_NAME]}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
        return self.async_show_form(
            step_id="irrigation", data_schema=_step_irrigation_schema(self._data)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartMowingOptionsFlow:
        return SmartMowingOptionsFlow()


class SmartMowingOptionsFlow(OptionsFlow):
    """Handle options for an existing Smart Mowing config entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_GDD_BASE_TEMP,
                    default=options.get(CONF_GDD_BASE_TEMP, DEFAULT_GDD_BASE_TEMP),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-10, max=20, step=0.5, unit_of_measurement="°C"
                    )
                ),
                vol.Optional(
                    CONF_GDD_THRESHOLD,
                    default=options.get(CONF_GDD_THRESHOLD, DEFAULT_GDD_THRESHOLD),
                ): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=500, step=1)),
                vol.Optional(
                    CONF_MOW_WINDOW_START,
                    default=options.get(
                        CONF_MOW_WINDOW_START, DEFAULT_MOW_WINDOW_START.isoformat()
                    ),
                ): selector.TimeSelector(),
                vol.Optional(
                    CONF_MOW_WINDOW_END,
                    default=options.get(CONF_MOW_WINDOW_END, DEFAULT_MOW_WINDOW_END.isoformat()),
                ): selector.TimeSelector(),
                vol.Optional(
                    CONF_ALLOWED_WEEKDAYS,
                    default=options.get(CONF_ALLOWED_WEEKDAYS, DEFAULT_ALLOWED_WEEKDAYS),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=WEEKDAY_OPTIONS, multiple=True)
                ),
                vol.Optional(
                    CONF_MIN_MOW_INTERVAL_HOURS,
                    default=options.get(
                        CONF_MIN_MOW_INTERVAL_HOURS, DEFAULT_MIN_MOW_INTERVAL_HOURS
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=96, step=1, unit_of_measurement="h")
                ),
                vol.Optional(
                    CONF_HEAT_LOCKOUT_TEMP,
                    default=options.get(CONF_HEAT_LOCKOUT_TEMP, DEFAULT_HEAT_LOCKOUT_TEMP),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=50, step=0.5, unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_DROUGHT_SOIL_MOISTURE_THRESHOLD,
                    default=options.get(
                        CONF_DROUGHT_SOIL_MOISTURE_THRESHOLD,
                        DEFAULT_DROUGHT_SOIL_MOISTURE_THRESHOLD,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%")
                ),
                vol.Optional(
                    CONF_DROUGHT_NO_RAIN_DAYS,
                    default=options.get(CONF_DROUGHT_NO_RAIN_DAYS, DEFAULT_DROUGHT_NO_RAIN_DAYS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="d")
                ),
                vol.Optional(
                    CONF_RAIN_STOP_THRESHOLD,
                    default=options.get(CONF_RAIN_STOP_THRESHOLD, DEFAULT_RAIN_STOP_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=20, step=0.1, unit_of_measurement="mm/h"
                    )
                ),
                vol.Optional(
                    CONF_RECENT_RAIN_HOURS,
                    default=options.get(CONF_RECENT_RAIN_HOURS, DEFAULT_RECENT_RAIN_HOURS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=48, step=1, unit_of_measurement="h")
                ),
                vol.Optional(
                    CONF_RECENT_RAIN_THRESHOLD,
                    default=options.get(CONF_RECENT_RAIN_THRESHOLD, DEFAULT_RECENT_RAIN_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=50, step=0.1, unit_of_measurement="mm")
                ),
                vol.Optional(
                    CONF_DEWPOINT_SPREAD_MIN,
                    default=options.get(CONF_DEWPOINT_SPREAD_MIN, DEFAULT_DEWPOINT_SPREAD_MIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=10, step=0.1, unit_of_measurement="K")
                ),
                vol.Optional(
                    CONF_HYSTERESIS_TEMP,
                    default=options.get(CONF_HYSTERESIS_TEMP, DEFAULT_HYSTERESIS_TEMP),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=5, step=0.1, unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_HYSTERESIS_DEWPOINT,
                    default=options.get(CONF_HYSTERESIS_DEWPOINT, DEFAULT_HYSTERESIS_DEWPOINT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=5, step=0.1, unit_of_measurement="K")
                ),
                vol.Optional(
                    CONF_HYSTERESIS_SOIL_MOISTURE,
                    default=options.get(
                        CONF_HYSTERESIS_SOIL_MOISTURE, DEFAULT_HYSTERESIS_SOIL_MOISTURE
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=20, step=0.5, unit_of_measurement="%")
                ),
                vol.Optional(
                    CONF_RELEASE_GRACE_MINUTES,
                    default=options.get(CONF_RELEASE_GRACE_MINUTES, DEFAULT_RELEASE_GRACE_MINUTES),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=180, step=5, unit_of_measurement="min")
                ),
                vol.Optional(
                    CONF_ONLY_DOCK_OWN_RUNS,
                    default=options.get(CONF_ONLY_DOCK_OWN_RUNS, DEFAULT_ONLY_DOCK_OWN_RUNS),
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

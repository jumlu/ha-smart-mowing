"""Constants for the Smart Mowing integration."""

from __future__ import annotations

from datetime import time

DOMAIN = "smart_mowing"

PLATFORMS = ["sensor", "binary_sensor", "switch"]

# --- Config entry keys (step 1, required) ---
CONF_NAME = "name"
CONF_MOWER_ENTITY = "mower_entity"
CONF_TEMPERATURE_ENTITY = "temperature_entity"

# --- Config entry keys (step 2, weather, optional) ---
CONF_RAIN_RATE_ENTITY = "rain_rate_entity"
CONF_RAIN_AMOUNT_ENTITY = "rain_amount_entity"
CONF_HUMIDITY_ENTITY = "humidity_entity"
CONF_DEWPOINT_ENTITY = "dewpoint_entity"
CONF_SOIL_MOISTURE_ENTITY = "soil_moisture_entity"
CONF_SOLAR_RADIATION_ENTITY = "solar_radiation_entity"

# --- Config entry keys (step 3, irrigation, optional) ---
CONF_IRRIGATION_ENTITIES = "irrigation_entities"
CONF_IRRIGATION_LOCKOUT_HOURS = "irrigation_lockout_hours"

# --- Options keys ---
CONF_GDD_BASE_TEMP = "gdd_base_temp"
CONF_GDD_THRESHOLD = "gdd_threshold"
CONF_MOW_WINDOW_START = "mow_window_start"
CONF_MOW_WINDOW_END = "mow_window_end"
CONF_ALLOWED_WEEKDAYS = "allowed_weekdays"
CONF_MIN_MOW_INTERVAL_HOURS = "min_mow_interval_hours"
CONF_HEAT_LOCKOUT_TEMP = "heat_lockout_temp"
CONF_DROUGHT_SOIL_MOISTURE_THRESHOLD = "drought_soil_moisture_threshold"
CONF_DROUGHT_NO_RAIN_DAYS = "drought_no_rain_days"
CONF_RAIN_STOP_THRESHOLD = "rain_stop_threshold"
CONF_RECENT_RAIN_HOURS = "recent_rain_hours"
CONF_RECENT_RAIN_THRESHOLD = "recent_rain_threshold"
CONF_DEWPOINT_SPREAD_MIN = "dewpoint_spread_min"
CONF_HYSTERESIS_TEMP = "hysteresis_temp"
CONF_HYSTERESIS_DEWPOINT = "hysteresis_dewpoint"
CONF_HYSTERESIS_SOIL_MOISTURE = "hysteresis_soil_moisture"
CONF_RELEASE_GRACE_MINUTES = "release_grace_minutes"
CONF_ONLY_DOCK_OWN_RUNS = "only_dock_own_runs"

# --- Defaults ---
DEFAULT_GDD_BASE_TEMP = 5.0
DEFAULT_GDD_THRESHOLD = 50.0
DEFAULT_MOW_WINDOW_START = time(10, 0)
DEFAULT_MOW_WINDOW_END = time(18, 0)
DEFAULT_ALLOWED_WEEKDAYS = ["0", "1", "2", "3", "4", "5", "6"]  # Mon..Sun
DEFAULT_MIN_MOW_INTERVAL_HOURS = 20
DEFAULT_HEAT_LOCKOUT_TEMP = 30.0
DEFAULT_DROUGHT_SOIL_MOISTURE_THRESHOLD = 15.0
DEFAULT_DROUGHT_NO_RAIN_DAYS = 10
DEFAULT_RAIN_STOP_THRESHOLD = 0.2
DEFAULT_RECENT_RAIN_HOURS = 6
DEFAULT_RECENT_RAIN_THRESHOLD = 1.0
DEFAULT_DEWPOINT_SPREAD_MIN = 2.0
DEFAULT_HYSTERESIS_TEMP = 0.5
DEFAULT_HYSTERESIS_DEWPOINT = 0.5
DEFAULT_HYSTERESIS_SOIL_MOISTURE = 3.0
DEFAULT_RELEASE_GRACE_MINUTES = 30
DEFAULT_IRRIGATION_LOCKOUT_HOURS = 3
DEFAULT_ONLY_DOCK_OWN_RUNS = True

# --- Growth model damping when no rain sensor is configured ---
NO_SOIL_SENSOR_DROUGHT_FACTOR = 0.3

# --- Timing intervals ---
EVALUATION_INTERVAL_MINUTES = 5
DAILY_ROLLOVER_HOUR = 0
DAILY_ROLLOVER_MINUTE = 0
DAILY_ROLLOVER_SECOND = 0

# --- Need percentage cap ---
NEED_PERCENT_CAP = 200.0

# --- Blocker keys ---
BLOCKER_OUTSIDE_WINDOW = "outside_window"
BLOCKER_RAINING = "raining"
BLOCKER_RECENT_RAIN = "recent_rain"
BLOCKER_IRRIGATION_ACTIVE = "irrigation_active"
BLOCKER_IRRIGATION_RECENT = "irrigation_recent"
BLOCKER_DEW = "dew"
BLOCKER_HEAT = "heat"
BLOCKER_DROUGHT = "drought"
BLOCKER_COOLDOWN = "cooldown"
BLOCKER_UNAVAILABLE_SOURCE = "unavailable_source"
BLOCKER_GRACE_PERIOD = "grace_period"

ALL_BLOCKERS = [
    BLOCKER_OUTSIDE_WINDOW,
    BLOCKER_RAINING,
    BLOCKER_RECENT_RAIN,
    BLOCKER_IRRIGATION_ACTIVE,
    BLOCKER_IRRIGATION_RECENT,
    BLOCKER_DEW,
    BLOCKER_HEAT,
    BLOCKER_DROUGHT,
    BLOCKER_COOLDOWN,
    BLOCKER_UNAVAILABLE_SOURCE,
    BLOCKER_GRACE_PERIOD,
]

# --- Events ---
EVENT_MOWING_STARTED = "smart_mowing_started"
EVENT_MOWING_ABORTED = "smart_mowing_aborted"
EVENT_MOWING_COMPLETED = "smart_mowing_completed"

# --- Services ---
SERVICE_FORCE_MOW = "force_mow"
SERVICE_RESET_GROWTH = "reset_growth"
SERVICE_SET_GROWTH = "set_growth"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_GROWTH_VALUE = "value"
ATTR_REASON = "reason"

# --- lawn_mower states we care about (from homeassistant.components.lawn_mower) ---
STATE_MOWING = "mowing"
STATE_DOCKED = "docked"
STATE_PAUSED = "paused"
STATE_ERROR = "error"

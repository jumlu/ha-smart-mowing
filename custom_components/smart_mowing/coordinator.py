"""Central event-driven state and calculation engine for Smart Mowing.

No DataUpdateCoordinator / polling is used. Re-evaluation is driven by
state-change events on the configured source entities plus a periodic
timer (temperature sampling, blocker re-evaluation) and a daily rollover
timer (GDD accumulation).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    ALL_BLOCKERS,
    BLOCKER_COOLDOWN,
    BLOCKER_DEW,
    BLOCKER_DROUGHT,
    BLOCKER_GRACE_PERIOD,
    BLOCKER_HEAT,
    BLOCKER_IRRIGATION_ACTIVE,
    BLOCKER_IRRIGATION_RECENT,
    BLOCKER_OUTSIDE_WINDOW,
    BLOCKER_RAINING,
    BLOCKER_RECENT_RAIN,
    BLOCKER_UNAVAILABLE_SOURCE,
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
    EVALUATION_INTERVAL_MINUTES,
    EVENT_MOWING_ABORTED,
    EVENT_MOWING_COMPLETED,
    EVENT_MOWING_STARTED,
    NEED_PERCENT_CAP,
    NO_SOIL_SENSOR_DROUGHT_FACTOR,
    STATE_DOCKED,
    STATE_MOWING,
)

_LOGGER = logging.getLogger(__name__)

# How long an irrigation entity must be continuously "off" before we trust
# it actually stopped, rather than just glitching due to an active rain
# sensor on the controller (observed to flap roughly every 30 min).
IRRIGATION_FLAP_DEBOUNCE_MINUTES = 35

# How long we keep rolling rain-amount samples for the "recent rain" window.
RAIN_HISTORY_MAX_HOURS = 24
# Minimum rain amount delta between samples to count as "it rained".
RAIN_SIGNIFICANT_DELTA = 0.05
# Hysteresis applied to the rain-rate stop/resume threshold.
RAIN_RATE_HYSTERESIS = 0.05


def clamp(value: float, low: float, high: float) -> float:
    """Clamp value into [low, high]."""
    return max(low, min(high, value))


def compute_daily_gdd(average_temp: float, base_temp: float) -> float:
    """Growing Degree Days for one day."""
    return max(0.0, average_temp - base_temp)


def compute_growth_factor(
    soil_moisture: float | None,
    drought_soil_threshold: float,
    rain_amount_configured: bool,
    days_since_rain: float | None,
    drought_no_rain_days: int,
) -> float:
    """Damping factor applied to daily GDD when water is limited."""
    factor = 1.0
    if soil_moisture is not None:
        factor *= clamp(soil_moisture / drought_soil_threshold, 0.0, 1.0)
    elif rain_amount_configured and days_since_rain is not None:
        if days_since_rain >= drought_no_rain_days:
            factor *= NO_SOIL_SENSOR_DROUGHT_FACTOR
    return factor


def below_with_hysteresis(
    value: float, threshold: float, hysteresis: float, was_blocked: bool
) -> bool:
    """True if value is below threshold, with hysteresis on the release side."""
    if was_blocked:
        return value < threshold + hysteresis
    return value < threshold


def above_with_hysteresis(
    value: float, threshold: float, hysteresis: float, was_blocked: bool
) -> bool:
    """True if value is above threshold, with hysteresis on the release side."""
    if was_blocked:
        return value > threshold - hysteresis
    return value > threshold


def _is_valid_state(state) -> bool:
    return state is not None and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)


def _float_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if not _is_valid_state(state):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


@dataclass
class SmartMowingRuntimeState:
    """Mutable runtime state, seeded by RestoreEntity-backed entities."""

    growth_index: float = 0.0
    daily_temp_sum: float = 0.0
    daily_temp_count: int = 0
    last_rollover_date: date | None = None
    last_mow_time: datetime | None = None
    next_mow_time: datetime | None = None
    automatic_enabled: bool = True
    mower_started_by_us: bool = False
    irrigation_last_seen_on: datetime | None = None
    rain_history: deque = field(default_factory=lambda: deque(maxlen=2000))
    last_rain_time: datetime | None = None
    blockers_previously_empty: bool = True
    release_since: datetime | None = None
    blocker_hysteresis_state: dict[str, bool] = field(default_factory=dict)
    active_blockers: list[str] = field(default_factory=list)
    wet: bool = False
    mow_allowed: bool = False
    mow_needed: bool = False
    need_percent: float = 0.0


class SmartMowingCoordinator:
    """Owns configuration, runtime state, listeners and the decision logic."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.state = SmartMowingRuntimeState()
        self._unsub_listeners: list[Any] = []
        self._update_listeners: list[Any] = []
        self.device_name: str = entry.data.get(CONF_NAME, entry.title)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.device_name,
            manufacturer="Smart Mowing",
            model="Lawn Area",
        )

    # ---------------------------------------------------------------- config
    def _cfg(self, key: str, default: Any = None) -> Any:
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    @property
    def mower_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_MOWER_ENTITY)

    @property
    def temperature_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_TEMPERATURE_ENTITY)

    @property
    def rain_rate_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_RAIN_RATE_ENTITY)

    @property
    def rain_amount_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_RAIN_AMOUNT_ENTITY)

    @property
    def humidity_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_HUMIDITY_ENTITY)

    @property
    def dewpoint_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_DEWPOINT_ENTITY)

    @property
    def soil_moisture_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_SOIL_MOISTURE_ENTITY)

    @property
    def solar_radiation_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_SOLAR_RADIATION_ENTITY)

    @property
    def irrigation_entity_ids(self) -> list[str]:
        return self.entry.data.get(CONF_IRRIGATION_ENTITIES, []) or []

    @property
    def gdd_base_temp(self) -> float:
        return float(self._cfg(CONF_GDD_BASE_TEMP, DEFAULT_GDD_BASE_TEMP))

    @property
    def gdd_threshold(self) -> float:
        return float(self._cfg(CONF_GDD_THRESHOLD, DEFAULT_GDD_THRESHOLD))

    @property
    def mow_window_start(self) -> time:
        return self._parse_time(self._cfg(CONF_MOW_WINDOW_START, DEFAULT_MOW_WINDOW_START))

    @property
    def mow_window_end(self) -> time:
        return self._parse_time(self._cfg(CONF_MOW_WINDOW_END, DEFAULT_MOW_WINDOW_END))

    @staticmethod
    def _parse_time(value: Any) -> time:
        if isinstance(value, time):
            return value
        return dt_util.parse_time(value) or DEFAULT_MOW_WINDOW_START

    @property
    def allowed_weekdays(self) -> list[str]:
        return self._cfg(CONF_ALLOWED_WEEKDAYS, DEFAULT_ALLOWED_WEEKDAYS)

    @property
    def min_mow_interval_hours(self) -> float:
        return float(self._cfg(CONF_MIN_MOW_INTERVAL_HOURS, DEFAULT_MIN_MOW_INTERVAL_HOURS))

    @property
    def heat_lockout_temp(self) -> float:
        return float(self._cfg(CONF_HEAT_LOCKOUT_TEMP, DEFAULT_HEAT_LOCKOUT_TEMP))

    @property
    def drought_soil_moisture_threshold(self) -> float:
        return float(
            self._cfg(
                CONF_DROUGHT_SOIL_MOISTURE_THRESHOLD,
                DEFAULT_DROUGHT_SOIL_MOISTURE_THRESHOLD,
            )
        )

    @property
    def drought_no_rain_days(self) -> int:
        return int(self._cfg(CONF_DROUGHT_NO_RAIN_DAYS, DEFAULT_DROUGHT_NO_RAIN_DAYS))

    @property
    def rain_stop_threshold(self) -> float:
        return float(self._cfg(CONF_RAIN_STOP_THRESHOLD, DEFAULT_RAIN_STOP_THRESHOLD))

    @property
    def recent_rain_hours(self) -> float:
        return float(self._cfg(CONF_RECENT_RAIN_HOURS, DEFAULT_RECENT_RAIN_HOURS))

    @property
    def recent_rain_threshold(self) -> float:
        return float(self._cfg(CONF_RECENT_RAIN_THRESHOLD, DEFAULT_RECENT_RAIN_THRESHOLD))

    @property
    def dewpoint_spread_min(self) -> float:
        return float(self._cfg(CONF_DEWPOINT_SPREAD_MIN, DEFAULT_DEWPOINT_SPREAD_MIN))

    @property
    def hysteresis_temp(self) -> float:
        return float(self._cfg(CONF_HYSTERESIS_TEMP, DEFAULT_HYSTERESIS_TEMP))

    @property
    def hysteresis_dewpoint(self) -> float:
        return float(self._cfg(CONF_HYSTERESIS_DEWPOINT, DEFAULT_HYSTERESIS_DEWPOINT))

    @property
    def hysteresis_soil_moisture(self) -> float:
        return float(self._cfg(CONF_HYSTERESIS_SOIL_MOISTURE, DEFAULT_HYSTERESIS_SOIL_MOISTURE))

    @property
    def release_grace_minutes(self) -> float:
        return float(self._cfg(CONF_RELEASE_GRACE_MINUTES, DEFAULT_RELEASE_GRACE_MINUTES))

    @property
    def irrigation_lockout_hours(self) -> float:
        return float(
            self.entry.data.get(CONF_IRRIGATION_LOCKOUT_HOURS, DEFAULT_IRRIGATION_LOCKOUT_HOURS)
        )

    @property
    def only_dock_own_runs(self) -> bool:
        return bool(self._cfg(CONF_ONLY_DOCK_OWN_RUNS, DEFAULT_ONLY_DOCK_OWN_RUNS))

    # ------------------------------------------------------------- lifecycle
    def add_update_listener(self, listener) -> None:
        """Register a callback invoked after every re-evaluation."""
        self._update_listeners.append(listener)

    async def async_setup(self) -> None:
        entities_to_watch = [
            eid
            for eid in (
                self.mower_entity_id,
                self.temperature_entity_id,
                self.rain_rate_entity_id,
                self.rain_amount_entity_id,
                self.humidity_entity_id,
                self.dewpoint_entity_id,
                self.soil_moisture_entity_id,
                self.solar_radiation_entity_id,
                *self.irrigation_entity_ids,
            )
            if eid
        ]
        if entities_to_watch:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, entities_to_watch, self._async_on_state_change
                )
            )
        self._unsub_listeners.append(
            async_track_time_interval(
                self.hass,
                self._async_on_timer,
                timedelta(minutes=EVALUATION_INTERVAL_MINUTES),
            )
        )
        self._unsub_listeners.append(
            async_track_time_change(
                self.hass, self._async_on_daily_rollover, hour=0, minute=0, second=0
            )
        )
        await self._async_evaluate()

    async def async_unload(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # --------------------------------------------------------------- events
    @callback
    def _async_on_state_change(self, event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self._async_evaluate())

    @callback
    def _async_on_timer(self, now: datetime) -> None:
        self._sample_temperature()
        self._sample_rain()
        self.hass.async_create_task(self._async_evaluate())

    async def _async_on_daily_rollover(self, now: datetime) -> None:
        self._roll_over_day()
        await self._async_evaluate()

    # ---------------------------------------------------------- temperature
    def _sample_temperature(self) -> None:
        temp = _float_state(self.hass, self.temperature_entity_id)
        if temp is None:
            return
        self.state.daily_temp_sum += temp
        self.state.daily_temp_count += 1

    def _sample_rain(self) -> None:
        now = dt_util.utcnow()
        amount = _float_state(self.hass, self.rain_amount_entity_id)
        rate = _float_state(self.hass, self.rain_rate_entity_id)
        if rate is not None and rate > 0:
            self.state.last_rain_time = now
        if amount is not None:
            history = self.state.rain_history
            if history:
                _, previous = history[-1]
                if amount + RAIN_SIGNIFICANT_DELTA < previous:
                    # counter reset (new day) - do not treat as negative rain
                    pass
                elif amount - previous >= RAIN_SIGNIFICANT_DELTA:
                    self.state.last_rain_time = now
            history.append((now, amount))
            cutoff = now - timedelta(hours=RAIN_HISTORY_MAX_HOURS)
            while history and history[0][0] < cutoff:
                history.popleft()

    def _rain_in_last_hours(self, hours: float) -> float:
        """Sum of positive rain-amount deltas within the last `hours`."""
        now = dt_util.utcnow()
        cutoff = now - timedelta(hours=hours)
        history = [item for item in self.state.rain_history if item[0] >= cutoff]
        total = 0.0
        for (_, prev), (_, cur) in zip(history, history[1:]):
            delta = cur - prev
            if delta > 0:
                total += delta
        return total

    def _days_since_rain(self) -> float | None:
        if self.state.last_rain_time is None:
            return None
        delta = dt_util.utcnow() - self.state.last_rain_time
        return delta.total_seconds() / 86400.0

    def _roll_over_day(self) -> None:
        if self.state.daily_temp_count == 0:
            self.state.last_rollover_date = dt_util.now().date()
            return
        average_temp = self.state.daily_temp_sum / self.state.daily_temp_count
        daily_gdd = compute_daily_gdd(average_temp, self.gdd_base_temp)
        soil_moisture = _float_state(self.hass, self.soil_moisture_entity_id)
        factor = compute_growth_factor(
            soil_moisture,
            self.drought_soil_moisture_threshold,
            self.rain_amount_entity_id is not None,
            self._days_since_rain(),
            self.drought_no_rain_days,
        )
        self.state.growth_index += daily_gdd * factor
        self.state.daily_temp_sum = 0.0
        self.state.daily_temp_count = 0
        self.state.last_rollover_date = dt_util.now().date()
        _LOGGER.debug(
            "%s: daily rollover avg_temp=%.2f gdd=%.2f factor=%.2f growth_index=%.2f",
            self.device_name,
            average_temp,
            daily_gdd,
            factor,
            self.state.growth_index,
        )

    # ------------------------------------------------------------- restore
    def restore_growth_index(self, value: float) -> None:
        self.state.growth_index = value

    def restore_last_mow_time(self, value: datetime | None) -> None:
        self.state.last_mow_time = value

    def restore_automatic_enabled(self, value: bool) -> None:
        self.state.automatic_enabled = value

    # ------------------------------------------------------------- actions
    def reset_growth(self) -> None:
        self.state.growth_index = 0.0

    def set_growth(self, value: float) -> None:
        self.state.growth_index = value

    async def async_set_automatic_enabled(self, enabled: bool) -> None:
        self.state.automatic_enabled = enabled
        await self._async_evaluate()

    # ----------------------------------------------------------- blockers
    def _mower_state(self) -> str | None:
        state = self.hass.states.get(self.mower_entity_id) if self.mower_entity_id else None
        if not _is_valid_state(state):
            return None
        return state.state

    def _required_sources_available(self) -> bool:
        temp = self.hass.states.get(self.temperature_entity_id) if self.temperature_entity_id else None
        mower = self.hass.states.get(self.mower_entity_id) if self.mower_entity_id else None
        return _is_valid_state(temp) and _is_valid_state(mower)

    def _compute_blockers(self, now: datetime) -> list[str]:
        blockers: list[str] = []
        hyst_state = self.state.blocker_hysteresis_state

        if not self._required_sources_available():
            blockers.append(BLOCKER_UNAVAILABLE_SOURCE)
            self.state.blocker_hysteresis_state = {k: (k in blockers) for k in ALL_BLOCKERS}
            return blockers

        local_now = dt_util.as_local(now)
        weekday = str(local_now.weekday())
        if weekday not in self.allowed_weekdays or not (
            self.mow_window_start <= local_now.time() <= self.mow_window_end
        ):
            blockers.append(BLOCKER_OUTSIDE_WINDOW)

        rain_rate = _float_state(self.hass, self.rain_rate_entity_id)
        if rain_rate is not None:
            was_blocked = hyst_state.get(BLOCKER_RAINING, False)
            if above_with_hysteresis(
                rain_rate, self.rain_stop_threshold, RAIN_RATE_HYSTERESIS, was_blocked
            ):
                blockers.append(BLOCKER_RAINING)

        recent_rain_amount = self._rain_in_last_hours(self.recent_rain_hours)
        if self.rain_amount_entity_id is not None and recent_rain_amount > self.recent_rain_threshold:
            blockers.append(BLOCKER_RECENT_RAIN)

        if self.irrigation_entity_ids:
            active_now = any(
                (state := self.hass.states.get(eid)) is not None and state.state == STATE_ON
                for eid in self.irrigation_entity_ids
            )
            if active_now:
                self.state.irrigation_last_seen_on = now
            last_on = self.state.irrigation_last_seen_on
            if last_on is not None:
                elapsed = now - last_on
                if elapsed < timedelta(minutes=IRRIGATION_FLAP_DEBOUNCE_MINUTES):
                    blockers.append(BLOCKER_IRRIGATION_ACTIVE)
                elif elapsed < timedelta(hours=self.irrigation_lockout_hours):
                    blockers.append(BLOCKER_IRRIGATION_RECENT)

        dewpoint = _float_state(self.hass, self.dewpoint_entity_id)
        temp = _float_state(self.hass, self.temperature_entity_id)
        if dewpoint is not None and temp is not None:
            spread = temp - dewpoint
            was_blocked = hyst_state.get(BLOCKER_DEW, False)
            if below_with_hysteresis(
                spread, self.dewpoint_spread_min, self.hysteresis_dewpoint, was_blocked
            ):
                blockers.append(BLOCKER_DEW)

        if temp is not None:
            was_blocked = hyst_state.get(BLOCKER_HEAT, False)
            if above_with_hysteresis(temp, self.heat_lockout_temp, self.hysteresis_temp, was_blocked):
                blockers.append(BLOCKER_HEAT)

        soil_moisture = _float_state(self.hass, self.soil_moisture_entity_id)
        if soil_moisture is not None:
            was_blocked = hyst_state.get(BLOCKER_DROUGHT, False)
            if below_with_hysteresis(
                soil_moisture,
                self.drought_soil_moisture_threshold,
                self.hysteresis_soil_moisture,
                was_blocked,
            ):
                blockers.append(BLOCKER_DROUGHT)
        elif self.rain_amount_entity_id is not None:
            days_since_rain = self._days_since_rain()
            if days_since_rain is not None and days_since_rain >= self.drought_no_rain_days:
                blockers.append(BLOCKER_DROUGHT)

        if self.state.last_mow_time is not None:
            elapsed_hours = (now - self.state.last_mow_time).total_seconds() / 3600.0
            if elapsed_hours < self.min_mow_interval_hours:
                blockers.append(BLOCKER_COOLDOWN)

        self.state.blocker_hysteresis_state = {k: (k in blockers) for k in ALL_BLOCKERS}
        return blockers

    def _apply_release_grace(self, blockers: list[str], now: datetime) -> list[str]:
        """Require a grace period after the last real blocker clears."""
        if blockers:
            self.state.release_since = None
            return blockers
        if self.state.release_since is None:
            self.state.release_since = now
        elapsed = now - self.state.release_since
        if elapsed < timedelta(minutes=self.release_grace_minutes):
            return [BLOCKER_GRACE_PERIOD]
        return []

    # ---------------------------------------------------------- evaluation
    async def _async_evaluate(self) -> None:
        now = dt_util.utcnow()
        raw_blockers = self._compute_blockers(now)
        blockers = self._apply_release_grace(raw_blockers, now)

        self.state.active_blockers = blockers
        self.state.wet = BLOCKER_RAINING in raw_blockers or BLOCKER_DEW in raw_blockers or BLOCKER_RECENT_RAIN in raw_blockers
        self.state.mow_allowed = not blockers
        self.state.mow_needed = self.state.growth_index >= self.gdd_threshold
        self.state.need_percent = min(
            NEED_PERCENT_CAP,
            (self.state.growth_index / self.gdd_threshold * 100.0) if self.gdd_threshold else 0.0,
        )
        self._compute_next_mow_estimate()

        await self._async_maybe_act(raw_blockers, now)

        for listener in self._update_listeners:
            listener()

    def _compute_next_mow_estimate(self) -> None:
        if self.state.mow_needed and self.state.mow_allowed:
            self.state.next_mow_time = dt_util.utcnow()
            return
        if self.state.mow_needed:
            # need is met, waiting on a blocker to clear - unknown ETA
            self.state.next_mow_time = None
            return
        remaining = self.gdd_threshold - self.state.growth_index
        if remaining <= 0 or self.state.daily_temp_count == 0:
            self.state.next_mow_time = None
            return
        avg_temp_so_far = self.state.daily_temp_sum / self.state.daily_temp_count
        daily_rate = compute_daily_gdd(avg_temp_so_far, self.gdd_base_temp)
        if daily_rate <= 0:
            self.state.next_mow_time = None
            return
        days_needed = remaining / daily_rate
        self.state.next_mow_time = dt_util.utcnow() + timedelta(days=days_needed)

    async def _async_maybe_act(self, raw_blockers: list[str], now: datetime) -> None:
        mower_state = self._mower_state()

        if mower_state == STATE_MOWING and BLOCKER_RAINING in raw_blockers:
            if not self.only_dock_own_runs or self.state.mower_started_by_us:
                await self._async_dock(reason=BLOCKER_RAINING)
            return

        if mower_state == STATE_DOCKED and self.state.mower_started_by_us:
            self.state.mower_started_by_us = False
            self.hass.bus.async_fire(EVENT_MOWING_COMPLETED, {"config_entry_id": self.entry.entry_id})

        if not self.state.automatic_enabled:
            return
        if not self.state.mow_needed or not self.state.mow_allowed:
            return
        if mower_state != STATE_DOCKED:
            return

        await self.async_start_mowing()

    async def async_start_mowing(self) -> None:
        if not self.mower_entity_id:
            return
        await self.hass.services.async_call(
            "lawn_mower", "start_mowing", {"entity_id": self.mower_entity_id}, blocking=True
        )
        self.state.mower_started_by_us = True
        self.state.last_mow_time = dt_util.utcnow()
        self.hass.bus.async_fire(EVENT_MOWING_STARTED, {"config_entry_id": self.entry.entry_id})

    async def _async_dock(self, reason: str) -> None:
        if not self.mower_entity_id:
            return
        await self.hass.services.async_call(
            "lawn_mower", "dock", {"entity_id": self.mower_entity_id}, blocking=True
        )
        self.state.mower_started_by_us = False
        self.hass.bus.async_fire(
            EVENT_MOWING_ABORTED, {"config_entry_id": self.entry.entry_id, "reason": reason}
        )

    async def async_force_mow(self) -> None:
        await self.async_start_mowing()

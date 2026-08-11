"""Unit tests for the pure growth-model functions in coordinator.py."""

from __future__ import annotations

import pytest

from custom_components.smart_mowing.const import NO_SOIL_SENSOR_DROUGHT_FACTOR
from custom_components.smart_mowing.coordinator import (
    above_with_hysteresis,
    below_with_hysteresis,
    clamp,
    compute_daily_gdd,
    compute_growth_factor,
)


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(11, 0, 10) == 10


@pytest.mark.parametrize(
    ("avg_temp", "base_temp", "expected"),
    [
        (15.0, 5.0, 10.0),
        (5.0, 5.0, 0.0),
        (2.0, 5.0, 0.0),
        (-5.0, 5.0, 0.0),
    ],
)
def test_compute_daily_gdd(avg_temp, base_temp, expected):
    assert compute_daily_gdd(avg_temp, base_temp) == expected


def test_growth_factor_full_soil_moisture():
    factor = compute_growth_factor(
        soil_moisture=30.0,
        drought_soil_threshold=15.0,
        rain_amount_configured=False,
        days_since_rain=None,
        drought_no_rain_days=10,
    )
    assert factor == 1.0


def test_growth_factor_partial_soil_moisture():
    factor = compute_growth_factor(
        soil_moisture=7.5,
        drought_soil_threshold=15.0,
        rain_amount_configured=False,
        days_since_rain=None,
        drought_no_rain_days=10,
    )
    assert factor == pytest.approx(0.5)


def test_growth_factor_no_soil_sensor_recent_rain():
    factor = compute_growth_factor(
        soil_moisture=None,
        drought_soil_threshold=15.0,
        rain_amount_configured=True,
        days_since_rain=2.0,
        drought_no_rain_days=10,
    )
    assert factor == 1.0


def test_growth_factor_no_soil_sensor_drought():
    factor = compute_growth_factor(
        soil_moisture=None,
        drought_soil_threshold=15.0,
        rain_amount_configured=True,
        days_since_rain=12.0,
        drought_no_rain_days=10,
    )
    assert factor == pytest.approx(NO_SOIL_SENSOR_DROUGHT_FACTOR)


def test_growth_factor_no_sensors_at_all():
    factor = compute_growth_factor(
        soil_moisture=None,
        drought_soil_threshold=15.0,
        rain_amount_configured=False,
        days_since_rain=None,
        drought_no_rain_days=10,
    )
    assert factor == 1.0


def test_below_with_hysteresis_engages_at_threshold():
    assert below_with_hysteresis(4.9, 5.0, 0.5, was_blocked=False) is True
    assert below_with_hysteresis(5.0, 5.0, 0.5, was_blocked=False) is False


def test_below_with_hysteresis_holds_until_past_offset():
    # already blocked at 4.9 (threshold 5.0); must rise above 5.5 to release
    assert below_with_hysteresis(5.2, 5.0, 0.5, was_blocked=True) is True
    assert below_with_hysteresis(5.6, 5.0, 0.5, was_blocked=True) is False


def test_above_with_hysteresis_engages_at_threshold():
    assert above_with_hysteresis(30.1, 30.0, 0.5, was_blocked=False) is True
    assert above_with_hysteresis(30.0, 30.0, 0.5, was_blocked=False) is False


def test_above_with_hysteresis_holds_until_past_offset():
    assert above_with_hysteresis(29.7, 30.0, 0.5, was_blocked=True) is True
    assert above_with_hysteresis(29.4, 30.0, 0.5, was_blocked=True) is False

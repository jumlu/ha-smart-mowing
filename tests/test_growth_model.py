"""Unit tests for the pure growth-model functions in coordinator.py."""

from __future__ import annotations

import pytest

from custom_components.smart_mowing.const import LIGHT_FACTOR_MIN, NO_SOIL_SENSOR_DROUGHT_FACTOR
from custom_components.smart_mowing.coordinator import (
    above_with_hysteresis,
    below_with_hysteresis,
    clamp,
    compute_daily_growth_mm,
    compute_growth_potential,
    compute_light_factor,
    compute_water_factor,
)


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(11, 0, 10) == 10


@pytest.mark.parametrize(
    ("avg_temp", "optimal_temp", "temp_variance", "expected"),
    [
        (20.0, 20.0, 5.5, 1.0),  # right at the optimum: full potential
        (25.5, 20.0, 5.5, pytest.approx(0.6065, abs=1e-3)),  # one variance above
        (14.5, 20.0, 5.5, pytest.approx(0.6065, abs=1e-3)),  # symmetric: one below
        (33.0, 20.0, 5.5, pytest.approx(0.0613, abs=1e-3)),  # heat: growth collapses
        (20.0, 20.0, 0.0, 0.0),  # zero variance is degenerate, not a divide-by-zero
    ],
)
def test_compute_growth_potential(avg_temp, optimal_temp, temp_variance, expected):
    assert compute_growth_potential(avg_temp, optimal_temp, temp_variance) == expected


def test_compute_daily_growth_mm_at_optimum_uses_full_max_rate():
    # GP == 1.0 at the optimum, so with no water/light damping the daily
    # growth is exactly max_growth_mm.
    growth = compute_daily_growth_mm(
        average_temp=20.0,
        optimal_temp=20.0,
        temp_variance=5.5,
        max_growth_mm=4.0,
        water_factor=1.0,
        light_factor=1.0,
    )
    assert growth == pytest.approx(4.0)


def test_compute_daily_growth_mm_combines_all_factors():
    growth = compute_daily_growth_mm(
        average_temp=20.0,
        optimal_temp=20.0,
        temp_variance=5.5,
        max_growth_mm=4.0,
        water_factor=0.5,
        light_factor=0.5,
    )
    assert growth == pytest.approx(1.0)


def test_compute_daily_growth_mm_heat_suppresses_growth_without_a_separate_lockout():
    # This is the core reason for switching off GDD: growth should collapse
    # at high heat purely from the temperature response, no extra correction.
    growth = compute_daily_growth_mm(
        average_temp=33.0,
        optimal_temp=20.0,
        temp_variance=5.5,
        max_growth_mm=4.0,
        water_factor=1.0,
        light_factor=1.0,
    )
    assert growth < 0.3


def test_water_factor_full_soil_moisture():
    factor = compute_water_factor(
        soil_moisture=30.0,
        drought_soil_threshold=15.0,
        rain_amount_configured=False,
        days_since_rain=None,
        drought_no_rain_days=10,
    )
    assert factor == 1.0


def test_water_factor_partial_soil_moisture():
    factor = compute_water_factor(
        soil_moisture=7.5,
        drought_soil_threshold=15.0,
        rain_amount_configured=False,
        days_since_rain=None,
        drought_no_rain_days=10,
    )
    assert factor == pytest.approx(0.5)


def test_water_factor_no_soil_sensor_recent_rain():
    factor = compute_water_factor(
        soil_moisture=None,
        drought_soil_threshold=15.0,
        rain_amount_configured=True,
        days_since_rain=2.0,
        drought_no_rain_days=10,
    )
    assert factor == 1.0


def test_water_factor_no_soil_sensor_drought():
    factor = compute_water_factor(
        soil_moisture=None,
        drought_soil_threshold=15.0,
        rain_amount_configured=True,
        days_since_rain=12.0,
        drought_no_rain_days=10,
    )
    assert factor == pytest.approx(NO_SOIL_SENSOR_DROUGHT_FACTOR)


def test_water_factor_no_sensors_at_all():
    factor = compute_water_factor(
        soil_moisture=None,
        drought_soil_threshold=15.0,
        rain_amount_configured=False,
        days_since_rain=None,
        drought_no_rain_days=10,
    )
    assert factor == 1.0


def test_light_factor_no_sensor_configured():
    assert compute_light_factor(None, 800.0) == 1.0


def test_light_factor_invalid_reference():
    assert compute_light_factor(500.0, 0.0) == 1.0


def test_light_factor_full_sun():
    assert compute_light_factor(800.0, 800.0) == 1.0


def test_light_factor_above_reference_is_capped():
    assert compute_light_factor(1200.0, 800.0) == 1.0


def test_light_factor_partial_sun():
    assert compute_light_factor(400.0, 800.0) == pytest.approx(0.5)


def test_light_factor_overcast_floors_instead_of_zeroing():
    assert compute_light_factor(0.0, 800.0) == LIGHT_FACTOR_MIN


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

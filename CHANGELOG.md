# Changelog

## 0.7.0 — 2026-10-28

### Added

- **Bundled dashboard card** `custom:smart-mowing-calendar-card`: a compact month view with mowed
  days as green circles and the planned next mow as a dashed orange circle, month navigation and
  a short summary. German/English follow the viewing user's language. The integration serves and
  loads the card itself, no separate HACS frontend install needed.
- **Option `calendar_language`** (de/en) for the event titles of the mow plan calendar. Defaults
  to the HA system language.

## 0.6.0 — 2026-10-28

### Added

- **Mow plan calendar** (`calendar.<name>_mow_plan`): the forecast next mow as one all-day
  event ("Mähen geplant" / "Mow planned") that moves with `sensor.<name>_next_mow`. Description
  carries the forecast time and the current mow need. Combine it with a calendar of past mows in
  any calendar card.

## 0.5.1 — 2026-10-28

### Fixed

- **`next_mow` forecast no longer drifts every few minutes.** It was "now + days remaining" and
  changed on every evaluation (~650 recorder rows a day). It is now anchored to the start of the
  day and rounded up to the full hour; while a mow is due it keeps the moment it became due.
- **No `unknown` forecast after a restart.** The forecast is computed while loading the stored
  state, before the sensor writes its first value.

## 0.5.0 — 2026-10-25

### Added

- **Frost lockout** (`frost` blocker): no mowing below `frost_lockout_temp` (default 4 °C), with
  the existing temperature hysteresis.
- **Winter dormancy** (`binary_sensor.<name>_winter_dormancy`): on after `dormancy_days`
  (default 5) consecutive days with modeled growth below `dormancy_growth_threshold_mm`
  (default 0.1 mm/day), off after the same number of days at or above it. Persisted across
  restarts, fires `smart_mowing_dormancy_changed`. Optional `dormancy_pauses_automatic`
  (default off) blocks automatic mowing while dormant (`dormant` blocker, forecast `unknown`).

## 0.4.0 — 2026-10-25

### Fixed

- **`mow_need` stuck at 200%.** The need was computed from the cumulative `growth_index`
  without subtracting the growth at the last mow, so it never dropped after mowing and the mower
  went out on every release (only `min_mow_interval_hours` held it back). The need is now
  `(growth_index − growth_index_at_last_mow) / growth_threshold_mm × 100`.
- **Baseline survives restarts.** Growth index, baseline, last mow and the growth-rate estimate
  are persisted in HA storage and loaded before the entities are created — no more `0 → 200%`
  flicker on restart/reload. Upgrading from an older version starts the need at 0 from the
  current growth index.
- **`last_mow` only on a confirmed mow.** `last_mow` and the baseline are set when the mower
  entity actually switches to `mowing`, not when `start_mowing` is sent. A start that isn't
  confirmed within 30 minutes is not counted, logs a warning and is retried after 60 minutes
  (max. 3 attempts per day).
- **Flap debouncing.** `mowing → docked → mowing` within 5 minutes and `paused → mowing` count as
  one run.
- **`next_mow` forecast no longer `unknown`.** Below 100% it is derived from the remaining growth
  and a moving average of the daily growth; at or above 100% it is "now" or the next moment the
  mow window/cooldown allows.

### Changed

- Runs started outside Smart Mowing (vendor app, mower schedule, by hand) now reset the need as
  well, independent of "Only dock runs started by Smart Mowing" — the grass was cut either way.
- `smart_mowing_started` fires when the mower confirms `mowing` on a run Smart Mowing started,
  not when the command is sent.
- `reset_growth` / `set_growth` now set the growth *since the last mow* (index restarts at the
  value, baseline at 0).
- Diagnostics include baseline, growth since mow, rate estimate and start-retry state.

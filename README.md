# Smart Mowing

Home Assistant custom integration that decides **when** a `lawn_mower` entity should run, based on
grass growth and weather — instead of a dumb daily schedule. It works with any `lawn_mower` entity,
regardless of vendor.

- Mows only once the lawn has actually grown enough (PACE Turf Growth Potential model).
- Never mows onto wet grass (rain, recent rain, dew).
- Aborts a running mow if rain starts, and docks the mower.
- Respects a mow-window, weekdays, heat lockout, frost lockout, drought lockout, irrigation
  lockout and a minimum interval between mows.
- Tells you when the lawn has gone into winter dormancy (time to winterize the mower).
- Survives Home Assistant restarts — the growth accumulator is not lost.

## Installation via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jumlu&repository=ha-smart-mowing&category=Integration)

1. Click the badge above (or HACS → Integrations → ⋮ → Custom repositories → add this repository
   URL, category "Integration").
2. Install "Smart Mowing", restart Home Assistant.
3. Settings → Devices & Services → **+ Add Integration** → search "Smart Mowing".

This repository is not (yet) in the default HACS store, so it has to be added as a custom
repository. The brand icon/logo ship directly in `custom_components/smart_mowing/brand/` (supported
since HA 2026.3 — no separate [home-assistant/brands](https://github.com/home-assistant/brands) PR
needed); source SVGs are kept in `.brand_assets/` for future edits.

Each config entry shows up as a card under Settings → Devices & Services → **Integrations**, with
the resulting device (e.g. "Smart Mowing Controller") grouping all of its entities underneath.

## Setup (Config Flow)

The setup dialog has three steps, one config entry per lawn area:

1. **Basics (required):** name, mower entity, temperature sensor.
   <!-- screenshot: config-flow-step-1.png -->
2. **Weather (optional, recommended):** rain rate, rain amount, humidity, dew point, soil
   moisture, solar radiation. Each picker is filtered to sensors with the matching HA device
   class (e.g. rain rate only shows `precipitation_intensity`/mm-per-hour sensors, not
   `precipitation`/mm accumulators) — if your sensor isn't offered, its integration likely
   doesn't set that device class, and picking the wrong-unit sensor by name alone would silently
   feed the wrong physical quantity into the growth/blocker math.
   <!-- screenshot: config-flow-step-2.png -->
3. **Irrigation (optional):** irrigation entities (any domain) and a lockout duration after
   irrigation ends.
   <!-- screenshot: config-flow-step-3.png -->

All thresholds (growth-model parameters, mow window, weekdays, minimum interval, heat/drought/rain
thresholds, hysteresis offsets, ...) can be changed afterwards without deleting the entry, via the
entry's **Configure** (options flow) dialog.

The integration runs with just a mower and a temperature sensor — every optional sensor makes the
decision more precise, but nothing is required beyond that minimal setup.

## The growth model (Growth Potential)

Grass growth is modeled with [PACE Turf's Growth Potential](https://www.paceturf.org/PTRI/Documents/0004.pdf),
the standard turf-management model for translating weather into growth — rather than Growing
Degree Days (GDD). GDD rises monotonically with temperature, so it peaks at exactly the point
(high heat) where cool-season grasses (Lolium, Poa, Festuca — the common lawn types in Central
Europe) actually stop growing; correcting for that would need a bolted-on bypass. Growth Potential
instead models growth as a bell curve centered on an optimal temperature:

```
GP = exp(-0.5 × ((avg_temp − optimal_temp) / temp_variance)²)   # 0..1
```

Each day, the integration computes the average of the configured temperature sensor, derives `GP`,
and turns it into a millimeter growth amount:

```
growth_mm = GP × max_growth_rate × water_factor × light_factor
```

- **`max_growth_rate`** (default 4 mm/day) is the growth rate at perfect conditions — the one
  number to tune if your lawn grows faster or slower than the default assumes.
- **`water_factor`** damps growth when water is limited: `soil_moisture / drought_threshold`
  (clamped to `[0, 1]`) if a soil-moisture sensor is configured, otherwise a fixed damping factor
  once a configured number of rain-free days has passed.
- **`light_factor`** damps growth on overcast days if a solar-radiation sensor is configured:
  `solar_radiation / reference`, clamped to `[0.3, 1]` — diffuse light still allows some growth,
  so it floors rather than zeroes out.

The result accumulates into `growth_index` (mm) at midnight. `growth_index` is a cumulative
total; the mow need is measured against a **baseline** — the `growth_index` value at the start of
the last mow:

```
mow_need = (growth_index − growth_index_at_last_mow) / growth_threshold_mm × 100   (capped at 200%)
```

Once the growth since the last mow reaches the configured threshold (default 4 mm — the classic
one-third rule is too coarse for a mulching mower that should take small amounts often), the lawn
is considered ready to mow. The baseline and `last_mow` are persisted (HA storage), so they
survive restarts and reloads.

### What counts as a mow

- A mow is counted when the mower entity **actually switches to `mowing`** — never when
  `start_mowing` is sent. If the mower doesn't report `mowing` within 30 minutes of the command,
  the attempt is not counted, a warning is logged, and Smart Mowing retries after 60 minutes;
  after 3 failed attempts it waits until the next day.
- **Every** run counts, including runs started from the vendor app, the mower's own schedule or
  by hand — independent of "Only dock runs started by Smart Mowing". The grass was cut either way,
  so the need must start over; otherwise Smart Mowing would immediately send the mower out again.
  (That option only governs whether a rain abort may dock a run.)
- Short flaps (`mowing → docked → mowing` within 5 minutes) and resuming from `paused` count as the
  same run.
- The baseline is set when the run starts. A run that gets rained out still counts — the mower
  has covered part of the lawn, and the minimum interval plus the need restart keep it from being
  sent straight out again.

Because the temperature response is a bell curve, growth collapses on its own during a hot spell —
no separate correction needed. The heat lockout below still exists, but purely to protect the
mower hardware from operating in extreme heat, independent of the growth model.

The cold side is different: growth gets very slow but never quite reaches zero (≈0.1 mm/day at
5 °C), so a mild winter week could still add up to a mow. Two things cover that:

- **Frost lockout** (default below 4 °C air temperature, with the temperature hysteresis): blocks
  mowing on frozen or frosted grass — cutting frozen blades damages them, and ground frost forms
  well before the air reaches 0 °C.
- **Winter dormancy** (`binary_sensor.<name>_winter_dormancy`): turns on once the modeled daily
  growth stays below 0.1 mm/day for 5 days in a row, and off again after 5 days in a row at or
  above it — so a single mild day in January or a cold snap in April doesn't flip it. It fires
  `smart_mowing_dormancy_changed` and is meant for a "winterize the mower" notification. By
  default it only informs; enable "Pause automatic mowing during winter dormancy" in the options
  to also block automatic mowing (blocker `dormant`) until spring.

## Entities

| Entity | Type | Description |
|---|---|---|
| `sensor.<name>_growth_index` | Sensor (`total`, restores across restarts) | Cumulative modeled growth in mm |
| `sensor.<name>_mow_need` | Sensor (%) | `(growth_index − baseline) / threshold × 100`, capped at 200% |
| `binary_sensor.<name>_mowing_allowed` | Binary sensor | AND of all lockouts; `blockers` attribute lists active reasons |
| `binary_sensor.<name>_grass_wet` | Binary sensor (`moisture`) | Standalone wetness assessment (rain/dew/recent rain) |
| `binary_sensor.<name>_winter_dormancy` | Binary sensor (persists across restarts) | Lawn has stopped growing for the season; attributes `streak_days`, `growth_rate_mm_per_day` |
| `switch.<name>_automatic` | Switch (restores across restarts) | Master switch — off disables all automatic action |
| `sensor.<name>_last_mow` | Sensor (`timestamp`) | When the mower last actually started mowing (any trigger) |
| `sensor.<name>_next_mow` | Sensor (`timestamp`) | Forecast of the next mow (see FAQ) |

All entities of a config entry are grouped under one device.

## Services

- `smart_mowing.force_mow` — start mowing now, bypassing all lockouts.
- `smart_mowing.reset_growth` — set the growth index and the mow need back to 0. Not needed after a
  manual mow any more — those are detected automatically.
- `smart_mowing.set_growth` — set the growth since the last mow to a specific value (calibration;
  the index restarts at that value with a baseline of 0).

## Events

- `smart_mowing_started` (fired once the mower confirms `mowing` on a run Smart Mowing started),
  `smart_mowing_aborted` (with `reason`), `smart_mowing_completed`,
  `smart_mowing_dormancy_changed` (with `dormant: true/false`).

## Reconfiguration and removal

Every field from the setup dialog — mower, temperature sensor, all weather and irrigation entities
— can be changed later via the config entry's **Reconfigure** option (Settings → Devices & Services
→ Smart Mowing → the lawn area → ⋮ → Reconfigure), without deleting and recreating the entry.
Threshold-only changes belong in **Configure** (options flow) instead.

To remove a lawn area, delete its config entry from Settings → Devices & Services. This unloads
the entities and stops the integration from acting on the configured mower; it does not change any
state on the mower or weather integrations themselves, since Smart Mowing only reads their entities
and calls their services — it doesn't own or configure them.

## Troubleshooting

Download **Settings → Devices & Services → Smart Mowing → the lawn area → Download diagnostics**
for a snapshot of the current configuration, every source entity's live value, and the coordinator's
internal state (growth index, active blockers, whether the current mow was started by this
integration, ...). That's the first thing to check before filing an issue.

- **Nothing happens at all:** check `switch.<name>_automatic` is on, and check
  `binary_sensor.<name>_mowing_allowed`'s `blockers` attribute for the active lockout(s).
- **A required sensor shows `unavailable_source` in blockers:** the mower or temperature entity is
  `unknown`/`unavailable` — the integration refuses to decide without them rather than guessing.
- **Growth index looks wrong after a restart:** growth index, baseline and last mow are kept in HA
  storage (`.storage/smart_mowing.<entry_id>`). After upgrading from a version before 0.4.0 the
  baseline is unknown, so the need starts at 0 from the current growth index.
- **A start never shows up as `last_mow`:** check the log for "did not report mowing" — the mower
  accepted `start_mowing` but never switched to `mowing`.
- **The mower keeps getting docked:** check for `smart_mowing_aborted` events and their `reason` —
  usually `raining`. If it's docking mows you started manually, verify "Only dock runs started by
  Smart Mowing" is enabled in the options.
- Log messages from this integration are tagged `custom_components.smart_mowing` — enable debug
  logging for that logger under Settings → System → Logs if you need more detail than diagnostics
  provides.

## FAQ

**Do I need all the weather sensors?** No. With just a temperature sensor and a mower, the
integration mows purely on a growth schedule inside the configured mow window. Every additional
sensor removes a blind spot (rain, drought, dew, irrigation).

**How do I change the temperature sensor, or add a rain sensor, after setup?** Settings → Devices
& Services → Smart Mowing → the lawn area → ⋮ → **Reconfigure**. This re-opens the same three-step
setup dialog, prefilled with your current values — change the temperature sensor in step 1, or
add/change the rain rate sensor and any other weather sensor in step 2. The entry, its entities,
and their history stay intact; nothing needs to be deleted and recreated.

**How is `sensor.<name>_next_mow` (the forecast) computed?** Below 100% need: "now + remaining mm /
expected growth per day", where the expected rate is a moving average of the recent daily growth
(falling back to today's temperatures right after setup). At or above 100%: "now" if mowing is
allowed, otherwise the next moment the minimum interval / grace period has passed and the mow
window is open. Weather lockouts can't be predicted and are ignored. It's recomputed on every
evaluation, so the timestamp shifts a little over time — a live re-estimate, not an appointment.

**Why didn't it mow even though `mow_need` is over 100%?** Check
`binary_sensor.<name>_mowing_allowed`'s `blockers` attribute — it lists every active lockout
(rain, dew, heat, frost, winter dormancy, drought, cooldown, irrigation, outside the mow window, a grace period after the
last blocker cleared, ...).

**Why does it ignore my Hydrawise switch flipping on/off every 30 minutes?** Hydrawise switch
states are known to be unreliable when the controller's own rain sensor is active — the
integration debounces irrigation state instead of reacting to the instantaneous value, so a single
flicker doesn't immediately clear the irrigation lockout.

**Will it dock a mow I started manually?** No, by default the integration only docks mows it
started itself (configurable via "Only dock runs started by Smart Mowing" in the options).

**What happens to progress if a mow gets rained out?** The run still counts as a mow (the need
restarts from the moment the mower actually started mowing), since part of the lawn was cut. If you
want an immediate retry, use `smart_mowing.force_mow` or `smart_mowing.set_growth`.

## Development

```bash
pip install -r requirements_test.txt
pytest tests/ -v
```

A `.devcontainer` is included, so this repository can be opened directly in a GitHub Codespace.

## License

MIT — see [LICENSE](LICENSE).

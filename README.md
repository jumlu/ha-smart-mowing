# Smart Mowing

Home Assistant custom integration that decides **when** a `lawn_mower` entity should run, based on
grass growth and weather — instead of a dumb daily schedule. It works with any `lawn_mower` entity,
regardless of vendor.

- Mows only once the lawn has actually grown enough (Growing Degree Days model).
- Never mows onto wet grass (rain, recent rain, dew).
- Aborts a running mow if rain starts, and docks the mower.
- Respects a mow-window, weekdays, heat lockout, drought lockout, irrigation lockout and a
  minimum interval between mows.
- Survives Home Assistant restarts — the growth accumulator is not lost.

## Installation via HACS

1. HACS → Integrations → ⋮ → Custom repositories → add this repository URL, category
   "Integration".
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

The result accumulates into `growth_index` (mm) at midnight. Once it reaches the configured
threshold (default 4 mm — the classic one-third rule is too coarse for a mulching mower that
should take small amounts often), the lawn is considered ready to mow. The accumulator resets to 0
only after a *successful* mow — a mow aborted by rain leaves the accumulated progress untouched,
since the grass didn't stop growing just because the mower got interrupted.

Because the temperature response is a bell curve, growth collapses on its own during a hot spell —
no separate correction needed. The heat lockout below still exists, but purely to protect the
mower hardware from operating in extreme heat, independent of the growth model.

## Entities

| Entity | Type | Description |
|---|---|---|
| `sensor.<name>_growth_index` | Sensor (`total`, restores across restarts) | Accumulated growth in mm since the last successful mow |
| `sensor.<name>_mow_need` | Sensor (%) | `growth_index / threshold × 100`, capped at 200% |
| `binary_sensor.<name>_mowing_allowed` | Binary sensor | AND of all lockouts; `blockers` attribute lists active reasons |
| `binary_sensor.<name>_grass_wet` | Binary sensor (`moisture`) | Standalone wetness assessment (rain/dew/recent rain) |
| `switch.<name>_automatic` | Switch (restores across restarts) | Master switch — off disables all automatic action |
| `sensor.<name>_last_mow` | Sensor (`timestamp`) | When the last mow (started by this integration) completed |
| `sensor.<name>_next_mow` | Sensor (`timestamp`) | Forecast of when need and permission will next coincide |

All entities of a config entry are grouped under one device.

## Services

- `smart_mowing.force_mow` — start mowing now, bypassing all lockouts.
- `smart_mowing.reset_growth` — set the growth index back to 0 (e.g. after a manual mow).
- `smart_mowing.set_growth` — set the growth index to a specific value (calibration).

## Events

- `smart_mowing_started`, `smart_mowing_aborted` (with `reason`), `smart_mowing_completed`.

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
- **Growth index looks wrong after a restart:** it's restored via each entity's last recorded
  state; if the growth index sensor was unavailable for a long time before restart (e.g. the
  integration was reloaded mid-day), the restored value only reflects whatever was last written.
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

**Why does `sensor.<name>_next_mow` (the forecast) change so often?** It's recomputed as "now +
estimated days remaining" on every evaluation, and evaluation runs on every state change of any
watched entity plus a periodic timer — so the timestamp keeps shifting forward even when nothing
meaningful changed. The days-remaining estimate itself also moves as today's running temperature
average updates, especially early in the day when only a few samples exist. This is expected: it's
a live re-estimate, not a fixed appointment.

**Why didn't it mow even though `mow_need` is over 100%?** Check
`binary_sensor.<name>_mowing_allowed`'s `blockers` attribute — it lists every active lockout
(rain, dew, heat, drought, cooldown, irrigation, outside the mow window, a grace period after the
last blocker cleared, ...).

**Why does it ignore my Hydrawise switch flipping on/off every 30 minutes?** Hydrawise switch
states are known to be unreliable when the controller's own rain sensor is active — the
integration debounces irrigation state instead of reacting to the instantaneous value, so a single
flicker doesn't immediately clear the irrigation lockout.

**Will it dock a mow I started manually?** No, by default the integration only docks mows it
started itself (configurable via "Only dock runs started by Smart Mowing" in the options).

**What happens to progress if a mow gets rained out?** Nothing — the growth accumulator is only
reset after a mow that actually completed, so an aborted run doesn't cost you accumulated growth.

## Development

```bash
pip install -r requirements_test.txt
pytest tests/ -v
```

A `.devcontainer` is included, so this repository can be opened directly in a GitHub Codespace.

## License

MIT — see [LICENSE](LICENSE).

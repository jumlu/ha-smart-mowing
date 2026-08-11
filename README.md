# Smart Mowing

Home Assistant custom integration (helper-style, like `generic_thermostat`) that decides **when**
a `lawn_mower` entity should run, based on grass growth and weather — instead of a dumb daily
schedule. It works with any `lawn_mower` entity, regardless of vendor.

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
3. Settings → Devices & Services → Add Integration → search "Smart Mowing".

This repository is not (yet) in the default HACS store, so it has to be added as a custom
repository. It also has no icon in [home-assistant/brands](https://github.com/home-assistant/brands)
yet — that's a separate PR against that repository and only affects the icon shown in HACS/the UI,
not functionality.

## Setup (Config Flow)

The setup dialog has three steps, one config entry per lawn area:

1. **Basics (required):** name, mower entity, temperature sensor.
   <!-- screenshot: config-flow-step-1.png -->
2. **Weather (optional, recommended):** rain rate, rain amount, humidity, dew point, soil
   moisture, solar radiation.
   <!-- screenshot: config-flow-step-2.png -->
3. **Irrigation (optional):** irrigation entities (any domain) and a lockout duration after
   irrigation ends.
   <!-- screenshot: config-flow-step-3.png -->

All thresholds (GDD base temperature, GDD threshold, mow window, weekdays, minimum interval,
heat/drought/rain thresholds, hysteresis offsets, ...) can be changed afterwards without deleting
the entry, via the entry's **Configure** (options flow) dialog.

The integration runs with just a mower and a temperature sensor — every optional sensor makes the
decision more precise, but nothing is required beyond that minimal setup.

## The growth model (Growing Degree Days)

Grass growth roughly tracks accumulated warmth above a base temperature at which growth starts
(cool-season grasses: ~5 °C). Each day, the integration computes
`gdd = max(0, tagesmitteltemperatur - basistemperatur)` from a running average of the configured
temperature sensor, and adds it to a `wachstumsindex` (growth index) accumulator at midnight. Once
the accumulator reaches the configured threshold (default 50 GDD), the lawn is considered ready to
mow. The accumulator resets to 0 only after a *successful* mow — a mow aborted by rain leaves the
accumulated progress untouched, since the grass didn't stop growing just because the mower got
interrupted.

If a soil-moisture sensor is configured, the daily GDD contribution is scaled down proportionally
to how dry the soil is (`bodenfeuchte / trockenheits_schwelle`, clamped to `[0, 1]`) — grass grows
slower when water is limited, whether or not there's a hard drought lockout in effect. Without a
soil sensor but with a rain-amount sensor, growth is dampened by a fixed factor after a configured
number of rain-free days. This means the "don't mow during a hot, dry spell" behaviour falls out
of the growth model itself — no rain, no growth, no need — on top of the explicit heat/drought
lockouts below.

## Entities

| Entity | Type | Description |
|---|---|---|
| `sensor.<name>_growth_index` | Sensor (`total`, restores across restarts) | Accumulated GDD since the last successful mow |
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

## FAQ

**Do I need all the weather sensors?** No. With just a temperature sensor and a mower, the
integration mows purely on a growth schedule inside the configured mow window. Every additional
sensor removes a blind spot (rain, drought, dew, irrigation).

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
